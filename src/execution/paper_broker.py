"""In-memory paper-trading broker for backtesting and safe live dry runs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .base import Broker, Order, OrderStatus, OrderType, Position


class PaperBroker(Broker):
    def __init__(self, starting_cash: float = 10_000.0):
        self.cash = starting_cash
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._last_prices: dict[str, float] = {}

    def set_price(self, symbol: str, price: float) -> None:
        """Feed the broker the latest market price so it can fill orders."""
        self._last_prices[symbol] = price

    def submit(self, order: Order) -> Order:
        order.id = order.id or str(uuid.uuid4())
        price = self._last_prices.get(order.symbol)
        if price is None:
            order.status = OrderStatus.REJECTED
            self._orders[order.id] = order
            return order

        fill = price
        if order.order_type == OrderType.LIMIT and order.limit_price is not None:
            if order.side == "buy" and price > order.limit_price:
                order.status = OrderStatus.PENDING
                self._orders[order.id] = order
                return order
            if order.side == "sell" and price < order.limit_price:
                order.status = OrderStatus.PENDING
                self._orders[order.id] = order
                return order
            fill = order.limit_price

        cost = fill * order.qty
        if order.side == "buy":
            if cost > self.cash:
                order.status = OrderStatus.REJECTED
                self._orders[order.id] = order
                return order
            self.cash -= cost
            pos = self._positions.get(order.symbol)
            if pos is None:
                self._positions[order.symbol] = Position(order.symbol, order.qty, fill)
            else:
                new_qty = pos.qty + order.qty
                pos.avg_price = (pos.avg_price * pos.qty + fill * order.qty) / new_qty
                pos.qty = new_qty
        else:  # sell
            pos = self._positions.get(order.symbol)
            if pos is None or pos.qty < order.qty:
                order.status = OrderStatus.REJECTED
                self._orders[order.id] = order
                return order
            self.cash += cost
            pos.qty -= order.qty
            if pos.qty == 0:
                del self._positions[order.symbol]

        order.status = OrderStatus.FILLED
        order.fill_price = fill
        order.filled_at = datetime.now(timezone.utc)
        self._orders[order.id] = order
        return order

    def cancel(self, order_id: str) -> None:
        order = self._orders.get(order_id)
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED

    def positions(self) -> dict[str, Position]:
        return dict(self._positions)

    def equity(self) -> float:
        mtm = sum(
            self._last_prices.get(sym, pos.avg_price) * pos.qty
            for sym, pos in self._positions.items()
        )
        return self.cash + mtm
