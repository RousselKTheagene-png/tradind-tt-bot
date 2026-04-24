"""Bollinger squeeze breakout strategy.

Enter when Bollinger bandwidth has been compressed (low volatility) and price
breaks out of the band, signalling the start of an expansion move.
"""
from __future__ import annotations

import pandas as pd

from .base import Side, Signal, Strategy
from .indicators import bollinger


class BollingerSqueeze(Strategy):
    name = "bollinger_squeeze"
    # Breakouts fire during regime transitions; trend-following after compression.
    tolerated_regimes = frozenset({"trending_up", "trending_down",
                                   "high_volatility", "unknown"})

    def __init__(self, period: int = 20, num_std: float = 2.0,
                 squeeze_lookback: int = 50, squeeze_percentile: float = 0.25,
                 squeeze_bars: int = 10, **kwargs):
        super().__init__(period=period, num_std=num_std,
                         squeeze_lookback=squeeze_lookback,
                         squeeze_percentile=squeeze_percentile,
                         squeeze_bars=squeeze_bars, **kwargs)
        self.period = period
        self.num_std = num_std
        self.squeeze_lookback = squeeze_lookback
        self.squeeze_percentile = squeeze_percentile
        self.squeeze_bars = squeeze_bars

    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        need = self.period + self.squeeze_lookback + self.squeeze_bars + 2
        if len(ohlcv) < need:
            return None

        close = ohlcv["close"]
        upper, mid, lower = bollinger(close, self.period, self.num_std)
        bandwidth = (upper - lower) / mid

        # Baseline = history strictly BEFORE the recent window, so a genuine
        # recent squeeze shows up as below the baseline percentile.
        end = -(self.squeeze_bars + 1)
        start = end - self.squeeze_lookback
        baseline = bandwidth.iloc[start:end]
        if baseline.isna().any() or baseline.empty:
            return None
        threshold = float(baseline.quantile(self.squeeze_percentile))
        recent = bandwidth.iloc[-(self.squeeze_bars + 1):-1]
        recent_min = float(recent.min())
        was_squeezed = recent_min <= threshold

        if not was_squeezed:
            return None

        prev_close = float(close.iloc[-2])
        curr_close = float(close.iloc[-1])
        prev_upper = float(upper.iloc[-2])
        curr_upper = float(upper.iloc[-1])
        prev_lower = float(lower.iloc[-2])
        curr_lower = float(lower.iloc[-1])

        if prev_close <= prev_upper and curr_close > curr_upper:
            return Signal(symbol, Side.BUY, 0.75, curr_close,
                          f"BB squeeze breakout above upper band (bw_min={recent_min:.4f})",
                          {"recent_min_bandwidth": recent_min, "threshold": threshold,
                           "upper": curr_upper, "mid": float(mid.iloc[-1])})
        if prev_close >= prev_lower and curr_close < curr_lower:
            return Signal(symbol, Side.SELL, 0.75, curr_close,
                          f"BB squeeze breakout below lower band (bw_min={recent_min:.4f})",
                          {"recent_min_bandwidth": recent_min, "threshold": threshold,
                           "lower": curr_lower, "mid": float(mid.iloc[-1])})
        return None
