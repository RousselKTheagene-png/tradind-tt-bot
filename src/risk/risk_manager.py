"""Risk management: position sizing and per-trade/daily caps."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class RiskLimits:
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_open_positions: int = 5
    max_drawdown_pct: float = 15.0
    default_stop_loss_pct: float = 2.0
    default_take_profit_pct: float = 4.0


@dataclass
class RiskState:
    equity_high_water: float
    realized_pnl_today: float = 0.0
    current_date: date = field(default_factory=date.today)
    open_positions: int = 0


class RiskManager:
    """Central gatekeeper for all new orders."""

    def __init__(self, starting_equity: float, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()
        self.state = RiskState(equity_high_water=starting_equity)
        self.starting_equity = starting_equity

    def roll_day(self, today: date) -> None:
        if today != self.state.current_date:
            self.state.current_date = today
            self.state.realized_pnl_today = 0.0

    def position_size(self, equity: float, entry: float, stop: float) -> float:
        """Return the quantity to trade given a per-trade risk budget.

        Risk = (entry - stop) * qty  ==  equity * max_risk_per_trade_pct / 100
        """
        risk_per_unit = abs(entry - stop)
        if risk_per_unit <= 0:
            return 0.0
        budget = equity * self.limits.max_risk_per_trade_pct / 100.0
        return budget / risk_per_unit

    def can_open(self, equity: float) -> tuple[bool, str]:
        if self.state.open_positions >= self.limits.max_open_positions:
            return False, "max open positions reached"
        daily_loss_pct = -self.state.realized_pnl_today / max(equity, 1e-9) * 100
        if daily_loss_pct >= self.limits.max_daily_loss_pct:
            return False, f"daily loss limit hit ({daily_loss_pct:.2f}%)"
        drawdown_pct = (self.state.equity_high_water - equity) / max(
            self.state.equity_high_water, 1e-9) * 100
        if drawdown_pct >= self.limits.max_drawdown_pct:
            return False, f"max drawdown hit ({drawdown_pct:.2f}%)"
        return True, "ok"

    def default_stop_take(self, entry: float, side: str) -> tuple[float, float]:
        sl_pct = self.limits.default_stop_loss_pct / 100.0
        tp_pct = self.limits.default_take_profit_pct / 100.0
        if side == "buy":
            return entry * (1 - sl_pct), entry * (1 + tp_pct)
        return entry * (1 + sl_pct), entry * (1 - tp_pct)

    def on_fill(self, equity: float) -> None:
        self.state.open_positions += 1
        self.state.equity_high_water = max(self.state.equity_high_water, equity)

    def on_close(self, pnl: float, equity: float) -> None:
        self.state.open_positions = max(0, self.state.open_positions - 1)
        self.state.realized_pnl_today += pnl
        self.state.equity_high_water = max(self.state.equity_high_water, equity)
