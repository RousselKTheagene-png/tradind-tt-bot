"""OANDA order-routing broker (practice + live)."""
from __future__ import annotations

from datetime import datetime, timezone

from .base import Broker, Order, OrderStatus, OrderType, Position


class OandaBroker(Broker):
    """Adapts oandapyV20's REST client to the Broker interface.

    OANDA treats long/short by signed unit counts: positive=buy, negative=sell.
    Position fills are reported in the order creation response as
    ``orderFillTransaction``; a missing fill transaction means the order is
    pending or was rejected.
    """

    def __init__(self, api_key: str = "", account_id: str = "",
                 environment: str = "practice"):
        from oandapyV20 import API

        if environment not in {"practice", "live"}:
            raise ValueError("environment must be 'practice' or 'live'")
        self.account_id = account_id
        self.environment = environment
        self.client = API(access_token=api_key, environment=environment)

    @staticmethod
    def _signed_units(side: str, qty: float) -> int:
        units = int(round(qty))
        if units <= 0:
            raise ValueError("qty must round to a positive integer number of units")
        return units if side == "buy" else -units

    def _build_body(self, order: Order) -> dict:
        units = self._signed_units(order.side, order.qty)
        common = {
            "instrument": order.symbol,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
        }
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("LIMIT order requires limit_price")
            return {"order": {"type": "LIMIT", "price": f"{order.limit_price}",
                              "timeInForce": "GTC", **{k: v for k, v in common.items()
                                                       if k != "timeInForce"}}}
        return {"order": {"type": "MARKET", **common}}

    def submit(self, order: Order) -> Order:
        from oandapyV20.endpoints import orders

        try:
            req = orders.OrderCreate(accountID=self.account_id, data=self._build_body(order))
            self.client.request(req)
            resp = req.response or {}
            fill = resp.get("orderFillTransaction")
            create = resp.get("orderCreateTransaction", {})

            order.id = str(create.get("id", "")) or str(resp.get("lastTransactionID", ""))
            if fill:
                order.status = OrderStatus.FILLED
                order.fill_price = float(fill.get("price", 0.0))
                order.filled_at = datetime.now(timezone.utc)
            elif resp.get("orderCancelTransaction"):
                order.status = OrderStatus.CANCELLED
            else:
                order.status = OrderStatus.PENDING
            return order
        except Exception as exc:  # bubble up a failed order in a consistent shape
            order.status = OrderStatus.REJECTED
            order.metadata["error"] = str(exc)
            return order

    def cancel(self, order_id: str) -> None:
        from oandapyV20.endpoints import orders

        req = orders.OrderCancel(accountID=self.account_id, orderID=order_id)
        self.client.request(req)

    def positions(self) -> dict[str, Position]:
        from oandapyV20.endpoints import positions as pos_ep

        req = pos_ep.OpenPositions(accountID=self.account_id)
        self.client.request(req)
        out: dict[str, Position] = {}
        for p in req.response.get("positions", []):
            sym = p.get("instrument", "")
            long_side = p.get("long", {}) or {}
            short_side = p.get("short", {}) or {}
            long_units = float(long_side.get("units", 0) or 0)
            short_units = float(short_side.get("units", 0) or 0)
            if long_units > 0:
                qty = long_units
                avg = float(long_side.get("averagePrice", 0) or 0)
            elif short_units < 0:
                qty = short_units  # negative
                avg = float(short_side.get("averagePrice", 0) or 0)
            else:
                continue
            out[sym] = Position(symbol=sym, qty=qty, avg_price=avg)
        return out

    def equity(self) -> float:
        from oandapyV20.endpoints import accounts

        req = accounts.AccountSummary(accountID=self.account_id)
        self.client.request(req)
        account = req.response.get("account", {})
        # OANDA exposes NAV (net asset value) including unrealised P&L.
        return float(account.get("NAV", account.get("balance", 0.0)))
