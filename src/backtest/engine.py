"""Event-driven historical replay engine.

Runs a Strategy against a historical OHLCV DataFrame and simulates order
execution through the PaperBroker. To avoid lookahead bias, signals produced
on bar `i` are filled at bar `i + 1`'s open.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..execution.base import Order, OrderType
from ..execution.cost_model import CostModel
from ..execution.paper_broker import PaperBroker
from ..risk.risk_manager import RiskLimits, RiskManager
from ..strategies.base import Side, Strategy
from .metrics import PerformanceReport, compute_metrics


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list[dict] = field(default_factory=list)
    report: PerformanceReport | None = None


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        symbol: str,
        starting_cash: float = 10_000.0,
        risk_limits: RiskLimits | None = None,
        warmup: int = 100,
        timeframe: str = "1h",
        cost_model: CostModel | None = None,
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.starting_cash = starting_cash
        self.warmup = warmup
        self.timeframe = timeframe
        self.cost_model = cost_model or CostModel()
        self.broker = PaperBroker(starting_cash=starting_cash, cost_model=self.cost_model)
        self.risk = RiskManager(starting_cash, risk_limits or RiskLimits())
        self._entry_price: float | None = None
        self._entry_qty: float = 0.0

    def _close_position(self, price: float) -> float | None:
        """Flatten any open position. Returns realized P&L (or None if flat)."""
        pos = self.broker.positions().get(self.symbol)
        if pos is None:
            return None
        qty = pos.qty
        entry = self._entry_price or pos.avg_price
        self.broker.submit(Order(symbol=self.symbol, side="sell", qty=qty,
                                 order_type=OrderType.MARKET))
        pnl = (price - entry) * qty
        self.risk.on_close(pnl, self.broker.equity())
        self._entry_price = None
        self._entry_qty = 0.0
        return pnl

    def run(self, ohlcv: pd.DataFrame) -> BacktestResult:
        if len(ohlcv) < self.warmup + 2:
            raise ValueError(f"Need at least {self.warmup + 2} bars, got {len(ohlcv)}")

        equity_samples: list[tuple[pd.Timestamp, float]] = []
        trade_pnls: list[float] = []
        trades: list[dict] = []
        pending_signal: Side | None = None

        for i in range(self.warmup, len(ohlcv) - 1):
            window = ohlcv.iloc[: i + 1]
            next_open = float(ohlcv["open"].iloc[i + 1])
            next_ts = ohlcv.index[i + 1]

            # Fill any signal queued from the previous bar at this bar's open.
            if pending_signal is not None:
                self.broker.set_price(self.symbol, next_open)
                if pending_signal == Side.BUY and self._entry_qty == 0:
                    stop, _take = self.risk.default_stop_take(next_open, "buy")
                    qty = self.risk.position_size(self.broker.equity(), next_open, stop)
                    if qty > 0:
                        self.broker.submit(Order(symbol=self.symbol, side="buy",
                                                 qty=qty, order_type=OrderType.MARKET))
                        self._entry_price = next_open
                        self._entry_qty = qty
                        self.risk.on_fill(self.broker.equity())
                        trades.append({"ts": next_ts, "side": "buy",
                                       "price": next_open, "qty": qty})
                elif pending_signal == Side.SELL and self._entry_qty > 0:
                    pnl = self._close_position(next_open)
                    if pnl is not None:
                        trade_pnls.append(pnl)
                        trades.append({"ts": next_ts, "side": "sell",
                                       "price": next_open, "qty": self._entry_qty,
                                       "pnl": pnl})
                pending_signal = None

            # Generate next signal from the closed bar.
            signal = self.strategy.generate_signal(self.symbol, window)
            if signal is not None and signal.side in (Side.BUY, Side.SELL):
                pending_signal = signal.side

            # Mark-to-market equity snapshot.
            self.broker.set_price(self.symbol, float(window["close"].iloc[-1]))
            equity_samples.append((ohlcv.index[i], self.broker.equity()))

        # Force-close any open position at the final close.
        final_price = float(ohlcv["close"].iloc[-1])
        self.broker.set_price(self.symbol, final_price)
        if self._entry_qty > 0:
            pnl = self._close_position(final_price)
            if pnl is not None:
                trade_pnls.append(pnl)
                trades.append({"ts": ohlcv.index[-1], "side": "sell",
                               "price": final_price, "qty": self._entry_qty,
                               "pnl": pnl, "forced_exit": True})

        equity_curve = pd.Series(
            [v for _, v in equity_samples],
            index=[t for t, _ in equity_samples],
            name="equity",
        )
        report = compute_metrics(equity_curve, trade_pnls, self.timeframe)
        return BacktestResult(equity_curve=equity_curve, trades=trades, report=report)
