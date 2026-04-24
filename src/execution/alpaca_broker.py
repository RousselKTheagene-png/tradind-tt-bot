"""Alpaca order-routing broker (paper + live)."""
from __future__ import annotations

from datetime import datetime, timezone

from .base import Broker, Order, OrderStatus, OrderType, Position


class AlpacaBroker(Broker):
    """Adapts alpaca-py's TradingClient to the Broker interface."""

    def __init__(self, api_key: str = "", api_secret: str = "", paper: bool = True):
        from alpaca.trading.client import TradingClient

        self.paper = paper
        self.client = TradingClient(api_key, api_secret, paper=paper)

    def _to_alpaca_side(self, side: str):
        from alpaca.trading.enums import OrderSide

        return OrderSide.BUY if side == "buy" else OrderSide.SELL

    def _build_request(self, order: Order):
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        common = dict(
            symbol=order.symbol,
            qty=order.qty,
            side=self._to_alpaca_side(order.side),
            time_in_force=TimeInForce.DAY,
        )
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("LIMIT order requires limit_price")
            return LimitOrderRequest(limit_price=order.limit_price, **common)
        return MarketOrderRequest(**common)

    def submit(self, order: Order) -> Order:
        try:
            req = self._build_request(order)
            resp = self.client.submit_order(req)
            order.id = str(resp.id)
            order.status = (
                OrderStatus.FILLED if str(resp.status).endswith("filled")
                else OrderStatus.PENDING
            )
            if resp.filled_avg_price is not None:
                order.fill_price = float(resp.filled_avg_price)
                order.filled_at = datetime.now(timezone.utc)
            return order
        except Exception as exc:  # bubble up a failed order in a consistent shape
            order.status = OrderStatus.REJECTED
            order.metadata["error"] = str(exc)
            return order

    def cancel(self, order_id: str) -> None:
        self.client.cancel_order_by_id(order_id)

    def positions(self) -> dict[str, Position]:
        out: dict[str, Position] = {}
        for p in self.client.get_all_positions():
            out[p.symbol] = Position(
                symbol=p.symbol,
                qty=float(p.qty),
                avg_price=float(p.avg_entry_price),
            )
        return out

    def equity(self) -> float:
        account = self.client.get_account()
        return float(account.equity)
