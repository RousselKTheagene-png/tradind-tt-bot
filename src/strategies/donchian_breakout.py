"""Donchian channel breakout strategy.

Classic turtle-style trend follower:
- BUY when close crosses above the highest high of the prior ``entry_period`` bars.
- SELL when close crosses below the lowest low of the prior ``entry_period`` bars.
"""
from __future__ import annotations

import pandas as pd

from .base import Side, Signal, Strategy


class DonchianBreakout(Strategy):
    name = "donchian_breakout"
    tolerated_regimes = frozenset({"trending_up", "trending_down",
                                   "high_volatility", "unknown"})

    def __init__(self, entry_period: int = 20, **kwargs):
        super().__init__(entry_period=entry_period, **kwargs)
        self.entry_period = entry_period

    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        if len(ohlcv) < self.entry_period + 2:
            return None

        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]

        # Channel over the *prior* N bars (exclude current to avoid lookahead).
        prior_high = high.shift(1).rolling(self.entry_period).max()
        prior_low = low.shift(1).rolling(self.entry_period).min()

        prev_close = float(close.iloc[-2])
        curr_close = float(close.iloc[-1])
        prev_hi = float(prior_high.iloc[-2])
        curr_hi = float(prior_high.iloc[-1])
        prev_lo = float(prior_low.iloc[-2])
        curr_lo = float(prior_low.iloc[-1])

        if prev_close <= prev_hi and curr_close > curr_hi:
            return Signal(symbol, Side.BUY, 0.7, curr_close,
                          f"Donchian breakout above {self.entry_period}-bar high",
                          {"channel_high": curr_hi, "channel_low": curr_lo})
        if prev_close >= prev_lo and curr_close < curr_lo:
            return Signal(symbol, Side.SELL, 0.7, curr_close,
                          f"Donchian breakdown below {self.entry_period}-bar low",
                          {"channel_high": curr_hi, "channel_low": curr_lo})
        return None
