"""Fee and slippage model applied at fill time by PaperBroker."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    """Linear fee/slippage model expressed in basis points (1 bp = 0.01%).

    Slippage is applied symmetrically: a BUY fills above the quote and a SELL
    below it. Fees are charged on notional (fill_price * qty) regardless of side.
    """

    fee_bps: float = 0.0
    slippage_bps: float = 0.0

    def apply_slippage(self, price: float, side: str) -> float:
        bump = price * (self.slippage_bps / 10_000.0)
        if side == "buy":
            return price + bump
        return max(price - bump, 0.0)

    def fee(self, fill_price: float, qty: float) -> float:
        return abs(fill_price * qty) * (self.fee_bps / 10_000.0)
