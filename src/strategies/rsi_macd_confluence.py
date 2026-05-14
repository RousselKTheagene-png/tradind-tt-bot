"""RSI reversion + MACD confluence strategy.

Fires only when an RSI mean-reversion trigger lines up with at least one MACD
confirmation in a small recent window. The MACD confirmations are:

  - bull/bear divergence (price extreme vs MACD-histogram extreme)
  - histogram momentum reversal (declining -> rising for bulls, vice versa)
  - MACD line crossing the zero line

The reason string lists which MACD confirmations were active, and the metadata
payload records the indicator values so the journal/dashboard can render them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Side, Signal, Strategy
from .indicators import macd, rsi
from .macd_divergence import _local_extrema


class RsiMacdConfluence(Strategy):
    name = "rsi_macd_confluence"
    # Reversal/reversion: useful in ranging markets and at trend exhaustion.
    tolerated_regimes = frozenset({"ranging", "trending_up",
                                   "trending_down", "unknown"})

    def __init__(self, rsi_period: int = 10, oversold: float = 30,
                 overbought: float = 70, fast: int = 12, slow: int = 26,
                 signal: int = 9, divergence_lookback: int = 60,
                 pivot_order: int = 3, hist_reversal_bars: int = 3,
                 zero_cross_lookback: int = 5, confirm_window: int = 12,
                 **kwargs):
        super().__init__(rsi_period=rsi_period, oversold=oversold,
                         overbought=overbought, fast=fast, slow=slow,
                         signal=signal, divergence_lookback=divergence_lookback,
                         pivot_order=pivot_order,
                         hist_reversal_bars=hist_reversal_bars,
                         zero_cross_lookback=zero_cross_lookback,
                         confirm_window=confirm_window, **kwargs)
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.divergence_lookback = divergence_lookback
        self.pivot_order = pivot_order
        self.hist_reversal_bars = hist_reversal_bars
        self.zero_cross_lookback = zero_cross_lookback
        self.confirm_window = confirm_window

    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        need = (self.slow + self.signal + self.divergence_lookback
                + 2 * self.pivot_order + 2)
        if len(ohlcv) < need:
            return None

        close = ohlcv["close"]
        r = rsi(close, self.rsi_period)
        macd_line, _, hist = macd(close, self.fast, self.slow, self.signal)

        price = float(close.iloc[-1])
        prev_r, curr_r = float(r.iloc[-2]), float(r.iloc[-1])

        # RSI mean-reversion triggers within confirm_window bars.
        r_recent = r.iloc[-self.confirm_window - 1:]
        rsi_long = bool(((r_recent.shift(1) < self.oversold)
                         & (r_recent >= self.oversold)).any())
        rsi_short = bool(((r_recent.shift(1) > self.overbought)
                          & (r_recent <= self.overbought)).any())

        # ----- MACD confirmations -----
        bull_div, bear_div = self._divergence(close, hist)
        hist_bull, hist_bear = self._hist_reversal(hist)
        zcross_up, zcross_dn = self._zero_cross(macd_line)

        long_confs = [(bull_div, "bull div"), (hist_bull, "hist reversal"),
                      (zcross_up, "MACD>0 cross")]
        short_confs = [(bear_div, "bear div"), (hist_bear, "hist reversal"),
                       (zcross_dn, "MACD<0 cross")]

        if rsi_long:
            active = [name for ok, name in long_confs if ok]
            if active:
                strength = min(0.5 + 0.15 * len(active), 0.95)
                return Signal(symbol, Side.BUY, strength, price,
                              "RSI reversion up + " + ", ".join(active),
                              {"rsi": curr_r, "prev_rsi": prev_r,
                               "macd": float(macd_line.iloc[-1]),
                               "hist": float(hist.iloc[-1]),
                               "confirmations": active})

        if rsi_short:
            active = [name for ok, name in short_confs if ok]
            if active:
                strength = min(0.5 + 0.15 * len(active), 0.95)
                return Signal(symbol, Side.SELL, strength, price,
                              "RSI reversion down + " + ", ".join(active),
                              {"rsi": curr_r, "prev_rsi": prev_r,
                               "macd": float(macd_line.iloc[-1]),
                               "hist": float(hist.iloc[-1]),
                               "confirmations": active})
        return None

    # -------- helpers --------
    def _divergence(self, close: pd.Series, hist: pd.Series) -> tuple[bool, bool]:
        wc = close.iloc[-self.divergence_lookback:]
        wh = hist.iloc[-self.divergence_lookback:]
        p_mins, p_maxs = _local_extrema(wc, self.pivot_order)
        h_mins, h_maxs = _local_extrema(wh, self.pivot_order)
        bull = bear = False
        if len(p_mins) >= 2 and len(h_mins) >= 2:
            p0, p1 = p_mins[-2], p_mins[-1]
            h0, h1 = h_mins[-2], h_mins[-1]
            recent = (len(wc) - 1 - p1) <= self.pivot_order + self.confirm_window
            bull = (wc.iloc[p1] < wc.iloc[p0]
                    and wh.iloc[h1] > wh.iloc[h0] and recent)
        if len(p_maxs) >= 2 and len(h_maxs) >= 2:
            p0, p1 = p_maxs[-2], p_maxs[-1]
            h0, h1 = h_maxs[-2], h_maxs[-1]
            recent = (len(wc) - 1 - p1) <= self.pivot_order + self.confirm_window
            bear = (wc.iloc[p1] > wc.iloc[p0]
                    and wh.iloc[h1] < wh.iloc[h0] and recent)
        return bull, bear

    def _hist_reversal(self, hist: pd.Series) -> tuple[bool, bool]:
        n = self.hist_reversal_bars
        tail = hist.iloc[-(n + 1 + self.confirm_window):]
        d = tail.diff()
        bull = bear = False
        for i in range(self.confirm_window + 1):
            end = len(d) - i
            if end < n + 1:
                continue
            seg = d.iloc[end - n - 1:end]
            decl = bool((seg.iloc[:-1] < 0).all())
            rise = bool(seg.iloc[-1] > 0)
            ris_seg = bool((seg.iloc[:-1] > 0).all())
            fall = bool(seg.iloc[-1] < 0)
            if decl and rise:
                bull = True
            if ris_seg and fall:
                bear = True
        return bull, bear

    def _zero_cross(self, macd_line: pd.Series) -> tuple[bool, bool]:
        tail = macd_line.iloc[-self.zero_cross_lookback - 1:]
        prev = tail.shift(1)
        up = bool(((prev <= 0) & (tail > 0)).any())
        dn = bool(((prev >= 0) & (tail < 0)).any())
        return up, dn
