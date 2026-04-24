"""Feature extraction for market-regime classification.

All features are computed from a standard OHLCV DataFrame and returned as
a single DataFrame aligned on the same index (NaN in the warmup rows).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..strategies.indicators import atr


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength (0-100)."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = ((up > down) & (up > 0)).astype(float) * up.clip(lower=0)
    minus_dm = ((down > up) & (down > 0)).astype(float) * down.clip(lower=0)

    tr_series = atr(df, period) * period  # close approximation of smoothed TR
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / tr_series.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / tr_series.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0.0)


def hurst(series: pd.Series, max_lag: int = 20) -> float:
    """Estimate the Hurst exponent of a single price series.

    H ~ 0.5 -> random walk, H > 0.5 -> trending, H < 0.5 -> mean-reverting.
    Requires at least ~max_lag*2 observations; returns NaN otherwise.
    """
    s = pd.Series(series).dropna().astype(float).values
    if len(s) < max_lag * 2:
        return float("nan")
    lags = range(2, max_lag)
    # Rescaled range: std of differences at lag `lag`
    tau = [np.sqrt(np.std(s[lag:] - s[:-lag])) for lag in lags]
    # log-log regression slope -> H estimate (empirical R/S approximation)
    log_lags = np.log(list(lags))
    log_tau = np.log(tau)
    slope, _ = np.polyfit(log_lags, log_tau, 1)
    return float(slope * 2.0)


def rolling_hurst(series: pd.Series, window: int = 64, max_lag: int = 20) -> pd.Series:
    out = pd.Series(index=series.index, dtype=float)
    for i in range(window, len(series) + 1):
        out.iloc[i - 1] = hurst(series.iloc[i - window: i], max_lag=max_lag)
    return out


def extract_features(
    ohlcv: pd.DataFrame,
    window: int = 20,
    adx_period: int = 14,
    hurst_window: int = 64,
) -> pd.DataFrame:
    """Return a DataFrame of engineered regime features."""
    close = ohlcv["close"]
    returns = close.pct_change()

    feats = pd.DataFrame(index=ohlcv.index)
    feats["adx"] = adx(ohlcv, period=adx_period)
    feats["atr_pct"] = atr(ohlcv, period=adx_period) / close
    feats["ret_mean"] = returns.rolling(window).mean()
    feats["ret_std"] = returns.rolling(window).std()
    feats["hurst"] = rolling_hurst(close, window=hurst_window)
    return feats
