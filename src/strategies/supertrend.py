"""Supertrend strategy with optional 200-EMA trend filter.

Port of the user's TradingView "Tame Buy-Sell" Pine Script into the bot's
Strategy interface. Fires a BUY/SELL on the bar where the Supertrend direction
flips (-1 -> 1 = up, 1 -> -1 = down). Optional confluence filters cut whipsaws:

- ``use_trend_filter``: longs only when close > EMA(``trend_ema``); shorts only
  when close < EMA(``trend_ema``).
- ``allow_shorts``: off by default; longs-only is friendlier for new traders.
- Stop and target distances are returned in ``Signal.metadata`` as ATR multiples
  so downstream risk/exec can size positions on a fixed-R basis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Side, Signal, Strategy
from .indicators import atr, ema


def _supertrend(df: pd.DataFrame, period: int, factor: float) -> pd.DataFrame:
    """Compute Supertrend bands and direction series.

    Returns a DataFrame indexed like ``df`` with columns ``trend`` (+1/-1) and
    ``line`` (the active Supertrend stop level).
    """
    a = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2.0
    up_basic = hl2 - factor * a
    dn_basic = hl2 + factor * a

    trend_up = up_basic.copy()
    trend_dn = dn_basic.copy()
    direction = pd.Series(np.ones(len(df), dtype=int), index=df.index)

    close = df["close"].values
    ub = up_basic.values.copy()
    db = dn_basic.values.copy()
    for i in range(1, len(df)):
        ub[i] = max(ub[i], ub[i - 1]) if close[i - 1] > ub[i - 1] else ub[i]
        db[i] = min(db[i], db[i - 1]) if close[i - 1] < db[i - 1] else db[i]

        if close[i] > db[i - 1]:
            direction.iloc[i] = 1
        elif close[i] < ub[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

    trend_up = pd.Series(ub, index=df.index)
    trend_dn = pd.Series(db, index=df.index)
    line = pd.Series(np.where(direction == 1, trend_up, trend_dn), index=df.index)
    return pd.DataFrame({"trend": direction, "line": line, "atr": a})


class Supertrend(Strategy):
    """Trend-following entry on Supertrend flip.

    Parameters
    ----------
    factor : float
        ATR multiplier for the Supertrend bands (default 3.0).
    period : int
        ATR period used for the Supertrend (default 7).
    atr_exit_period : int
        ATR period used for the suggested stop/target distances (default 14).
    sl_mult : float
        Initial stop-loss distance in ATR(``atr_exit_period``) units (default 1.5).
    tp_mult : float
        Take-profit distance in ATR(``atr_exit_period``) units. Keep
        ``tp_mult >= 2 * sl_mult`` for a positive expectancy (default 3.0).
    use_trend_filter : bool
        Require price > EMA(``trend_ema``) for longs and < for shorts.
    trend_ema : int
        EMA length for the trend filter (default 200).
    allow_shorts : bool
        Permit short entries (default False; safer for beginners).
    """

    name = "supertrend"
    tolerated_regimes = frozenset({"trending_up", "trending_down",
                                   "high_volatility", "unknown"})

    def __init__(self, factor: float = 3.0, period: int = 7,
                 atr_exit_period: int = 14, sl_mult: float = 1.5,
                 tp_mult: float = 3.0, use_trend_filter: bool = True,
                 trend_ema: int = 200, allow_shorts: bool = False, **kwargs):
        super().__init__(factor=factor, period=period,
                         atr_exit_period=atr_exit_period, sl_mult=sl_mult,
                         tp_mult=tp_mult, use_trend_filter=use_trend_filter,
                         trend_ema=trend_ema, allow_shorts=allow_shorts, **kwargs)
        self.factor = float(factor)
        self.period = int(period)
        self.atr_exit_period = int(atr_exit_period)
        self.sl_mult = float(sl_mult)
        self.tp_mult = float(tp_mult)
        self.use_trend_filter = bool(use_trend_filter)
        self.trend_ema = int(trend_ema)
        self.allow_shorts = bool(allow_shorts)

    def _min_bars(self) -> int:
        need = max(self.period, self.atr_exit_period) + 2
        if self.use_trend_filter:
            need = max(need, self.trend_ema + 2)
        return need

    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        if len(ohlcv) < self._min_bars():
            return None

        st = _supertrend(ohlcv, self.period, self.factor)
        trend = st["trend"]
        if pd.isna(trend.iloc[-1]) or pd.isna(trend.iloc[-2]):
            return None

        prev = int(trend.iloc[-2])
        curr = int(trend.iloc[-1])
        flip_up = prev == -1 and curr == 1
        flip_down = prev == 1 and curr == -1
        if not (flip_up or flip_down):
            return None

        close = ohlcv["close"]
        price = float(close.iloc[-1])
        atr_exit = float(atr(ohlcv, self.atr_exit_period).iloc[-1])
        st_line = float(st["line"].iloc[-1])

        ema_val = float(ema(close, self.trend_ema).iloc[-1]) if self.use_trend_filter else None
        if self.use_trend_filter:
            if flip_up and price <= ema_val:
                return None
            if flip_down and price >= ema_val:
                return None

        if flip_down and not self.allow_shorts:
            return None

        side = Side.BUY if flip_up else Side.SELL
        sl = price - self.sl_mult * atr_exit if flip_up else price + self.sl_mult * atr_exit
        tp = price + self.tp_mult * atr_exit if flip_up else price - self.tp_mult * atr_exit
        why = ("Supertrend flipped UP" if flip_up else "Supertrend flipped DOWN")
        if self.use_trend_filter:
            why += f"; close {'>' if flip_up else '<'} EMA({self.trend_ema})"
        why += f"; SL {self.sl_mult}xATR, TP {self.tp_mult}xATR"

        meta = {
            "supertrend": st_line,
            "atr": atr_exit,
            "stop_loss": float(sl),
            "take_profit": float(tp),
            "rr_ratio": float(self.tp_mult / self.sl_mult) if self.sl_mult else None,
        }
        if self.use_trend_filter:
            meta["trend_ema"] = ema_val
        return Signal(symbol, side, 0.7, price, why, meta)
