"""RSI mean-reversion strategy."""
from __future__ import annotations

import pandas as pd

from .base import Side, Signal, Strategy
from .indicators import rsi


class RsiReversion(Strategy):
    name = "rsi_reversion"
    # Mean-reversion: only fire in ranging regimes (and unknown as a fallback).
    tolerated_regimes = frozenset({"ranging", "unknown"})

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70, **kwargs):
        super().__init__(period=period, oversold=oversold, overbought=overbought, **kwargs)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        if len(ohlcv) < self.period + 2:
            return None

        close = ohlcv["close"]
        r = rsi(close, self.period)
        prev, curr = float(r.iloc[-2]), float(r.iloc[-1])
        price = float(close.iloc[-1])

        if prev < self.oversold <= curr:
            return Signal(symbol, Side.BUY, 0.6, price,
                          f"RSI crossed up through {self.oversold}", {"rsi": curr})
        if prev > self.overbought >= curr:
            return Signal(symbol, Side.SELL, 0.6, price,
                          f"RSI crossed down through {self.overbought}", {"rsi": curr})
        return None
