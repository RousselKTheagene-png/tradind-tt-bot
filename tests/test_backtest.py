"""Backtest engine and metrics unit tests."""
import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import compute_metrics
from src.strategies.ema_crossover import EmaCrossover
from src.strategies.rsi_reversion import RsiReversion


def _make_ohlcv(n: int = 400, seed: int = 0, drift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, 0.01, n)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": rng.integers(1, 1000, n)},
                        index=idx)


def test_metrics_on_flat_equity():
    equity = pd.Series([100.0] * 50)
    report = compute_metrics(equity, trade_pnls=[], timeframe="1h")
    assert report.total_return_pct == 0.0
    assert report.max_drawdown_pct == 0.0
    assert report.num_trades == 0
    assert report.sharpe == 0.0


def test_metrics_positive_trend():
    equity = pd.Series(np.linspace(100, 120, 50))
    report = compute_metrics(equity, trade_pnls=[5, -2, 3], timeframe="1h")
    assert report.total_return_pct == pytest.approx(20.0, abs=1e-6)
    assert report.num_trades == 3
    assert report.win_rate_pct == pytest.approx(66.6666, abs=1e-2)
    assert report.profit_factor == pytest.approx(8 / 2, rel=1e-6)


def test_metrics_drawdown_detected():
    equity = pd.Series([100, 110, 120, 90, 95, 100])
    report = compute_metrics(equity, trade_pnls=[], timeframe="1h")
    assert report.max_drawdown_pct == pytest.approx(-25.0, abs=1e-6)


def test_engine_requires_sufficient_data():
    engine = BacktestEngine(strategy=EmaCrossover(fast=5, slow=10),
                            symbol="BTC/USDT", warmup=50)
    with pytest.raises(ValueError):
        engine.run(_make_ohlcv(n=10))


def test_engine_runs_and_produces_report():
    df = _make_ohlcv(n=400, drift=0.0005)
    engine = BacktestEngine(strategy=EmaCrossover(fast=10, slow=30),
                            symbol="BTC/USDT", warmup=50, timeframe="1h")
    result = engine.run(df)
    assert result.report is not None
    assert not result.equity_curve.empty
    # Equity curve has one point per bar after warmup (excluding the last bar).
    assert len(result.equity_curve) == len(df) - 50 - 1
    # All trades are dict entries with at minimum side and price
    for trade in result.trades:
        assert "side" in trade and "price" in trade


def test_engine_closes_open_position_at_end():
    df = _make_ohlcv(n=300, drift=0.002)  # strong uptrend -> likely to leave longs open
    engine = BacktestEngine(strategy=EmaCrossover(fast=5, slow=20),
                            symbol="BTC/USDT", warmup=50)
    result = engine.run(df)
    # After the forced exit, no position should remain.
    assert engine.broker.positions() == {}


def test_engine_works_with_rsi_strategy():
    df = _make_ohlcv(n=400)
    engine = BacktestEngine(strategy=RsiReversion(period=14),
                            symbol="BTC/USDT", warmup=50)
    result = engine.run(df)
    assert result.report is not None
    assert result.report.num_trades >= 0
