"""Regime filter integration with strategies and backtest engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine
from src.intelligence.regime import Regime, RegimeClassifier
from src.strategies.base import Side, Signal, Strategy
from src.strategies.ema_crossover import EmaCrossover
from src.strategies.rsi_reversion import RsiReversion


def _ranging(n: int = 400, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + 2 * np.sin(np.linspace(0, 10 * np.pi, n)) + rng.normal(0, 0.3, n)
    high = close + np.abs(rng.normal(0, 0.2, n))
    low = close - np.abs(rng.normal(0, 0.2, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": rng.integers(1, 1000, n)}, index=idx)


def _trending(n: int = 400, drift: float = 0.008, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, 0.003, n)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.001, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.001, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": rng.integers(1, 1000, n)}, index=idx)


# --- Strategy.accepts_regime ------------------------------------------------

def test_strategy_default_accepts_all_regimes():
    class Any_(Strategy):
        name = "any"
        def generate_signal(self, symbol, ohlcv):
            return None
    s = Any_()
    for r in Regime:
        assert s.accepts_regime(r.value)


def test_ema_crossover_rejects_ranging():
    s = EmaCrossover()
    assert s.accepts_regime("trending_up")
    assert s.accepts_regime("trending_down")
    assert not s.accepts_regime("ranging")
    assert not s.accepts_regime("high_volatility")


def test_rsi_reversion_rejects_trending():
    s = RsiReversion()
    assert s.accepts_regime("ranging")
    assert not s.accepts_regime("trending_up")
    assert not s.accepts_regime("high_volatility")


# --- Engine-level filter -----------------------------------------------------

class _AlwaysBuyStrategy(Strategy):
    """Emits a BUY on every bar so we can count how many make it through."""
    name = "always_buy"

    def __init__(self, tolerated: frozenset | None = None):
        super().__init__()
        self.tolerated_regimes = tolerated

    def generate_signal(self, symbol, ohlcv):
        return Signal(symbol, Side.BUY, 1.0, float(ohlcv["close"].iloc[-1]),
                      "always", {})


def test_engine_blocks_signals_outside_tolerated_regime():
    df = _ranging()
    # Strategy only tolerates an impossible regime -> every signal is blocked.
    strat = _AlwaysBuyStrategy(tolerated=frozenset({"__never__"}))
    engine = BacktestEngine(
        strategy=strat, symbol="BTC/USDT", warmup=100, timeframe="1h",
        regime_filter=RegimeClassifier(method="rules"),
    )
    result = engine.run(df)
    assert result.regime_blocks > 0
    assert result.report.num_trades == 0


def test_engine_without_filter_lets_everything_through():
    df = _ranging()
    strat = _AlwaysBuyStrategy(tolerated=frozenset({"trending_up"}))  # should only matter with filter
    engine = BacktestEngine(strategy=strat, symbol="BTC/USDT", warmup=100, timeframe="1h")
    result = engine.run(df)
    assert result.regime_blocks == 0


def test_engine_allows_signals_in_tolerated_regime():
    df = _trending()
    strat = _AlwaysBuyStrategy(tolerated=frozenset({"trending_up", "unknown"}))
    engine = BacktestEngine(
        strategy=strat, symbol="BTC/USDT", warmup=100, timeframe="1h",
        regime_filter=RegimeClassifier(method="rules"),
    )
    result = engine.run(df)
    # At least some signals should have gotten through (exactly how many depends
    # on the regime oscillating, but num_trades >= 1).
    assert result.report.num_trades >= 1
