"""Classic EMA crossover strategy."""
from __future__ import annotations

import pandas as pd

from .base import Side, Signal, Strategy
from .indicators import ema


class EmaCrossover(Strategy):
    name = "ema_crossover"

    def __init__(self, fast: int = 20, slow: int = 50, **kwargs):
        super().__init__(fast=fast, slow=slow, **kwargs)
        self.fast = fast
        self.slow = slow

    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        if len(ohlcv) < self.slow + 2:
            return None

        close = ohlcv["close"]
        fast_ema = ema(close, self.fast)
        slow_ema = ema(close, self.slow)

        prev_diff = fast_ema.iloc[-2] - slow_ema.iloc[-2]
        curr_diff = fast_ema.iloc[-1] - slow_ema.iloc[-1]
        price = float(close.iloc[-1])

        if prev_diff <= 0 < curr_diff:
            return Signal(symbol, Side.BUY, 0.7, price,
                          f"fast EMA({self.fast}) crossed above slow EMA({self.slow})",
                          {"fast": float(fast_ema.iloc[-1]), "slow": float(slow_ema.iloc[-1])})
        if prev_diff >= 0 > curr_diff:
            return Signal(symbol, Side.SELL, 0.7, price,
                          f"fast EMA({self.fast}) crossed below slow EMA({self.slow})",
                          {"fast": float(fast_ema.iloc[-1]), "slow": float(slow_ema.iloc[-1])})
        return None
