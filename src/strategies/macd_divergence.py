"""MACD histogram divergence strategy.

Looks for price/MACD-histogram divergence over a recent lookback window to catch
potential reversals.

- Bullish divergence: most recent price trough is *lower* than the prior trough,
  but the corresponding MACD histogram trough is *higher* -> BUY.
- Bearish divergence: most recent price peak is *higher* than the prior peak,
  but the corresponding MACD histogram peak is *lower* -> SELL.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Side, Signal, Strategy
from .indicators import macd


def _local_extrema(series: pd.Series, order: int = 3) -> tuple[list[int], list[int]]:
    """Return (min_idx, max_idx) positions in the series.

    A point is a local minimum if it is <= its ``order`` neighbours on each side
    (and strictly < at least one side). Symmetric for maxima.
    """
    values = series.to_numpy()
    n = len(values)
    mins: list[int] = []
    maxs: list[int] = []
    for i in range(order, n - order):
        window = values[i - order:i + order + 1]
        if np.isnan(window).any():
            continue
        center = values[i]
        if center == window.min() and center < window[0]:
            mins.append(i)
        elif center == window.max() and center > window[0]:
            maxs.append(i)
    return mins, maxs


class MacdDivergence(Strategy):
    name = "macd_divergence"
    # Reversal signal: useful across several regimes except pure chop.
    tolerated_regimes = frozenset({"trending_up", "trending_down",
                                   "ranging", "unknown"})

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9,
                 lookback: int = 60, pivot_order: int = 3, **kwargs):
        super().__init__(fast=fast, slow=slow, signal=signal,
                         lookback=lookback, pivot_order=pivot_order, **kwargs)
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.lookback = lookback
        self.pivot_order = pivot_order

    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        need = self.slow + self.signal + self.lookback + 2 * self.pivot_order + 2
        if len(ohlcv) < need:
            return None

        close = ohlcv["close"]
        _, _, hist = macd(close, self.fast, self.slow, self.signal)

        window_close = close.iloc[-self.lookback:]
        window_hist = hist.iloc[-self.lookback:]

        price_mins, price_maxs = _local_extrema(window_close, self.pivot_order)
        hist_mins, hist_maxs = _local_extrema(window_hist, self.pivot_order)

        price = float(close.iloc[-1])

        # Bullish divergence: last two price troughs + corresponding hist troughs
        if len(price_mins) >= 2 and len(hist_mins) >= 2:
            p_prev, p_curr = price_mins[-2], price_mins[-1]
            h_prev, h_curr = hist_mins[-2], hist_mins[-1]
            price_lower_low = window_close.iloc[p_curr] < window_close.iloc[p_prev]
            hist_higher_low = window_hist.iloc[h_curr] > window_hist.iloc[h_prev]
            # Only fire if the most recent trough is near the current bar.
            recent = (self.lookback - 1 - p_curr) <= self.pivot_order + 1
            if price_lower_low and hist_higher_low and recent:
                return Signal(symbol, Side.BUY, 0.65, price,
                              "Bullish MACD divergence (price LL, hist HL)",
                              {"price_low": float(window_close.iloc[p_curr]),
                               "prev_price_low": float(window_close.iloc[p_prev]),
                               "hist_low": float(window_hist.iloc[h_curr]),
                               "prev_hist_low": float(window_hist.iloc[h_prev])})

        # Bearish divergence: last two price peaks + corresponding hist peaks
        if len(price_maxs) >= 2 and len(hist_maxs) >= 2:
            p_prev, p_curr = price_maxs[-2], price_maxs[-1]
            h_prev, h_curr = hist_maxs[-2], hist_maxs[-1]
            price_higher_high = window_close.iloc[p_curr] > window_close.iloc[p_prev]
            hist_lower_high = window_hist.iloc[h_curr] < window_hist.iloc[h_prev]
            recent = (self.lookback - 1 - p_curr) <= self.pivot_order + 1
            if price_higher_high and hist_lower_high and recent:
                return Signal(symbol, Side.SELL, 0.65, price,
                              "Bearish MACD divergence (price HH, hist LH)",
                              {"price_high": float(window_close.iloc[p_curr]),
                               "prev_price_high": float(window_close.iloc[p_prev]),
                               "hist_high": float(window_hist.iloc[h_curr]),
                               "prev_hist_high": float(window_hist.iloc[h_prev])})
        return None
