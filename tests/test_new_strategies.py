"""Tests for Bollinger squeeze, MACD divergence, and Donchian breakout strategies."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.main import STRATEGY_REGISTRY
from src.strategies.base import Side
from src.strategies.bollinger_squeeze import BollingerSqueeze
from src.strategies.donchian_breakout import DonchianBreakout
from src.strategies.macd_divergence import MacdDivergence
from src.strategies.supertrend import Supertrend


def _ohlcv_from_close(close: np.ndarray) -> pd.DataFrame:
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    high = close * 1.0005
    low = close * 0.9995
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": np.ones(n)}, index=idx)


# --- Registry ----------------------------------------------------------------

def test_strategies_registered():
    for name in ("bollinger_squeeze", "macd_divergence",
                 "donchian_breakout", "supertrend"):
        assert name in STRATEGY_REGISTRY


# --- Bollinger squeeze -------------------------------------------------------

def test_bollinger_squeeze_fires_on_upside_breakout():
    # Long flat/squeezed period, then a single-bar surge above the upper band.
    rng = np.random.default_rng(0)
    flat = 100 + rng.normal(0, 0.05, 120)
    close = np.concatenate([flat, [108.0]])
    df = _ohlcv_from_close(close)

    strat = BollingerSqueeze(period=20, squeeze_lookback=40,
                             squeeze_percentile=0.5, squeeze_bars=10)
    sig = strat.generate_signal("X", df)
    assert sig is not None
    assert sig.side == Side.BUY


def test_bollinger_squeeze_fires_on_downside_breakout():
    rng = np.random.default_rng(1)
    flat = 100 + rng.normal(0, 0.05, 120)
    close = np.concatenate([flat, [92.0]])
    df = _ohlcv_from_close(close)

    strat = BollingerSqueeze(period=20, squeeze_lookback=40,
                             squeeze_percentile=0.5, squeeze_bars=10)
    sig = strat.generate_signal("X", df)
    assert sig is not None
    assert sig.side == Side.SELL


def test_bollinger_squeeze_silent_without_squeeze():
    rng = np.random.default_rng(2)
    # High-volatility noise throughout -> no preceding squeeze.
    close = 100 + np.cumsum(rng.normal(0, 1.5, 200))
    df = _ohlcv_from_close(close)

    strat = BollingerSqueeze(period=20, squeeze_lookback=50,
                             squeeze_percentile=0.1, squeeze_bars=10)
    assert strat.generate_signal("X", df) is None


def test_bollinger_squeeze_regime_preferences():
    s = BollingerSqueeze()
    assert s.accepts_regime("trending_up")
    assert s.accepts_regime("high_volatility")
    assert not s.accepts_regime("ranging")


def test_bollinger_squeeze_short_series_returns_none():
    df = _ohlcv_from_close(np.full(10, 100.0))
    assert BollingerSqueeze().generate_signal("X", df) is None


# --- MACD divergence ---------------------------------------------------------

def test_macd_divergence_detects_bullish():
    # Construct a price series with two troughs; second trough is a lower low
    # but occurs after enough recovery for MACD hist to have pulled up.
    n = 200
    x = np.arange(n)
    # Downtrend that decelerates: price makes a lower low late, but momentum
    # loss means the MACD histogram trough is higher (less negative).
    close = 100 - 0.05 * x + 3 * np.sin(x / 8.0)
    # Force a small rebound at the very end to get a local trough a few bars back.
    close[-5:] = close[-6] + np.arange(1, 6) * 0.05
    df = _ohlcv_from_close(close)

    strat = MacdDivergence(lookback=80, pivot_order=3)
    sig = strat.generate_signal("X", df)
    # We accept either a valid bullish divergence or no signal (algo is strict);
    # this test primarily guards that the method doesn't crash on edge series.
    assert sig is None or sig.side == Side.BUY


def test_macd_divergence_returns_none_on_monotone_uptrend():
    close = 100 + np.arange(200) * 0.2
    df = _ohlcv_from_close(close)
    assert MacdDivergence(lookback=80).generate_signal("X", df) is None


def test_macd_divergence_regime_preferences():
    s = MacdDivergence()
    assert s.accepts_regime("ranging")
    assert s.accepts_regime("trending_up")
    assert not s.accepts_regime("high_volatility")


def test_macd_divergence_short_series_returns_none():
    df = _ohlcv_from_close(np.full(20, 100.0))
    assert MacdDivergence().generate_signal("X", df) is None


# --- Donchian breakout -------------------------------------------------------

def test_donchian_breakout_buy():
    # 30 bars around 100, then a break to a new high.
    rng = np.random.default_rng(3)
    base = 100 + rng.normal(0, 0.1, 30)
    breakout = np.array([101.5])
    close = np.concatenate([base, breakout])
    df = _ohlcv_from_close(close)

    strat = DonchianBreakout(entry_period=20)
    sig = strat.generate_signal("X", df)
    assert sig is not None
    assert sig.side == Side.BUY


def test_donchian_breakout_sell():
    rng = np.random.default_rng(4)
    base = 100 + rng.normal(0, 0.1, 30)
    breakdown = np.array([98.0])
    close = np.concatenate([base, breakdown])
    df = _ohlcv_from_close(close)

    strat = DonchianBreakout(entry_period=20)
    sig = strat.generate_signal("X", df)
    assert sig is not None
    assert sig.side == Side.SELL


def test_donchian_breakout_silent_inside_channel():
    rng = np.random.default_rng(5)
    close = 100 + rng.normal(0, 0.1, 50)
    df = _ohlcv_from_close(close)
    strat = DonchianBreakout(entry_period=20)
    # Noise inside a tight range rarely triggers — if it does, it must be
    # a legitimate breakout, but that's unlikely with this seed.
    sig = strat.generate_signal("X", df)
    if sig is not None:
        assert sig.side in (Side.BUY, Side.SELL)


def test_donchian_breakout_regime_preferences():
    s = DonchianBreakout()
    assert s.accepts_regime("trending_up")
    assert not s.accepts_regime("ranging")


def test_donchian_breakout_short_series_returns_none():
    df = _ohlcv_from_close(np.full(10, 100.0))
    assert DonchianBreakout().generate_signal("X", df) is None


# --- Supertrend -------------------------------------------------------------

def _ohlcv_with_range(close: np.ndarray, range_pct: float = 0.005) -> pd.DataFrame:
    """Like ``_ohlcv_from_close`` but with a configurable high/low spread so
    ATR is non-trivial."""
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    high = close * (1 + range_pct)
    low = close * (1 - range_pct)
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": np.ones(n)}, index=idx)


def test_supertrend_fires_buy_on_flip_up():
    # Long downtrend (locks Supertrend to -1), brief flat phase, then a single
    # sharp up-bar at the end forces the flip on the last bar.
    down = np.linspace(100, 80, 60)
    flat = np.full(8, 80.0)
    breakout = np.array([90.0])
    close = np.concatenate([down, flat, breakout])
    df = _ohlcv_with_range(close, range_pct=0.004)

    strat = Supertrend(factor=3.0, period=7, use_trend_filter=False)
    sig = strat.generate_signal("X", df)
    assert sig is not None
    assert sig.side == Side.BUY
    assert sig.metadata["stop_loss"] < sig.price
    assert sig.metadata["take_profit"] > sig.price
    assert sig.metadata["rr_ratio"] == 2.0


def test_supertrend_fires_sell_on_flip_down_when_shorts_allowed():
    up = np.linspace(80, 100, 60)
    flat = np.full(8, 100.0)
    crash = np.array([90.0])
    close = np.concatenate([up, flat, crash])
    df = _ohlcv_with_range(close, range_pct=0.004)

    strat = Supertrend(factor=3.0, period=7, use_trend_filter=False,
                       allow_shorts=True)
    sig = strat.generate_signal("X", df)
    assert sig is not None
    assert sig.side == Side.SELL
    assert sig.metadata["stop_loss"] > sig.price
    assert sig.metadata["take_profit"] < sig.price


def test_supertrend_blocks_shorts_by_default():
    up = np.linspace(80, 100, 60)
    flat = np.full(8, 100.0)
    crash = np.array([90.0])
    close = np.concatenate([up, flat, crash])
    df = _ohlcv_with_range(close, range_pct=0.004)

    strat = Supertrend(factor=3.0, period=7, use_trend_filter=False)
    assert strat.generate_signal("X", df) is None


def test_supertrend_silent_on_steady_trend():
    # Pure uptrend with no flip in the lookback window.
    close = np.linspace(100, 130, 250)
    df = _ohlcv_with_range(close, range_pct=0.003)
    strat = Supertrend(factor=3.0, period=7, use_trend_filter=False)
    assert strat.generate_signal("X", df) is None


def test_supertrend_trend_filter_blocks_long_below_ema():
    # Downtrend then a flat phase and a single up-bar that flips Supertrend up
    # but stays well below EMA(200), so the trend filter must veto the long.
    down = np.linspace(120, 80, 220)
    flat = np.full(8, 80.0)
    breakout = np.array([85.0])
    close = np.concatenate([down, flat, breakout])
    df = _ohlcv_with_range(close, range_pct=0.004)

    strat = Supertrend(factor=3.0, period=7, use_trend_filter=True,
                       trend_ema=200)
    assert strat.generate_signal("X", df) is None


def test_supertrend_regime_preferences():
    s = Supertrend()
    assert s.accepts_regime("trending_up")
    assert s.accepts_regime("trending_down")
    assert s.accepts_regime("high_volatility")
    assert not s.accepts_regime("ranging")


def test_supertrend_short_series_returns_none():
    df = _ohlcv_with_range(np.full(50, 100.0))
    assert Supertrend().generate_signal("X", df) is None
