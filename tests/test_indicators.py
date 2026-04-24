"""Smoke tests for indicator math."""
import numpy as np
import pandas as pd

from src.strategies.indicators import atr, bollinger, ema, macd, rsi, sma, stochastic


def _fake_ohlcv(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.01, n)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": rng.integers(1, 1000, n)})


def test_sma_matches_rolling_mean():
    s = pd.Series(range(50), dtype=float)
    assert sma(s, 5).iloc[-1] == s.iloc[-5:].mean()


def test_ema_converges():
    s = pd.Series([1.0] * 100)
    assert abs(ema(s, 10).iloc[-1] - 1.0) < 1e-9


def test_rsi_bounds():
    df = _fake_ohlcv()
    r = rsi(df["close"]).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_macd_shapes():
    df = _fake_ohlcv()
    m, s, h = macd(df["close"])
    assert len(m) == len(s) == len(h) == len(df)


def test_bollinger_bands():
    df = _fake_ohlcv()
    upper, mid, lower = bollinger(df["close"])
    valid = upper.dropna().index
    assert (upper.loc[valid] >= mid.loc[valid]).all()
    assert (mid.loc[valid] >= lower.loc[valid]).all()


def test_atr_positive():
    df = _fake_ohlcv()
    a = atr(df).dropna()
    assert (a >= 0).all()


def test_stochastic_shape():
    df = _fake_ohlcv()
    k, d = stochastic(df)
    assert len(k) == len(d) == len(df)
