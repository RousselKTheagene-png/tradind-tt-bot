"""Crypto order-routing broker backed by ccxt (Binance, Coinbase, Kraken, ...).

Spot-only. For derivatives / futures, subclass and override ``_fetch_positions``
and ``equity`` to use the exchange's margin/positions endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .base import Broker, Order, OrderStatus, OrderType, Position


class CcxtBroker(Broker):
    """Adapts a ccxt exchange client to the Broker interface.

    Equity is computed as:
        sum(total_balance[asset] * last_price(asset/base_currency))
    using ticker prices for non-base holdings. This reflects the mark-to-market
    value of the spot portfolio in ``base_currency`` units.
    """

    def __init__(self, exchange: str = "binance", api_key: str = "",
                 api_secret: str = "", base_currency: str = "USDT"):
        import ccxt  # lazy import mirrors CryptoProvider

        klass = getattr(ccxt, exchange)
        self.exchange = exchange
        self.base_currency = base_currency
        self.client = klass({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })

    # ----- order routing -------------------------------------------------

    def submit(self, order: Order) -> Order:
        try:
            otype = "limit" if order.order_type == OrderType.LIMIT else "market"
            price = order.limit_price if otype == "limit" else None
            if otype == "limit" and price is None:
                raise ValueError("LIMIT order requires limit_price")
            resp = self.client.create_order(
                symbol=order.symbol,
                type=otype,
                side=order.side,
                amount=order.qty,
                price=price,
            )
            order.id = str(resp.get("id", ""))
            order.status = self._map_status(resp.get("status"))
            fill = resp.get("average") or resp.get("price")
            if fill is not None:
                order.fill_price = float(fill)
                order.filled_at = datetime.now(timezone.utc)
            return order
        except Exception as exc:  # keep a consistent failed-order shape
            order.status = OrderStatus.REJECTED
            order.metadata["error"] = str(exc)
            return order

    @staticmethod
    def _map_status(ccxt_status) -> OrderStatus:
        if ccxt_status in ("closed", "filled"):
            return OrderStatus.FILLED
        if ccxt_status in ("canceled", "cancelled"):
            return OrderStatus.CANCELLED
        if ccxt_status in ("rejected", "expired"):
            return OrderStatus.REJECTED
        return OrderStatus.PENDING

    def cancel(self, order_id: str) -> None:
        # ccxt requires symbol for many venues; leave to metadata if needed.
        self.client.cancel_order(order_id)

    # ----- account state -------------------------------------------------

    def _safe_price(self, symbol: str) -> float:
        try:
            ticker = self.client.fetch_ticker(symbol)
            return float(ticker.get("last") or 0.0)
        except Exception:
            return 0.0

    def _non_zero_totals(self) -> dict[str, float]:
        bal = self.client.fetch_balance() or {}
        total = bal.get("total") or {}
        return {asset: float(amt) for asset, amt in total.items()
                if amt and float(amt) != 0.0}

    def positions(self) -> dict[str, Position]:
        """Reconstruct spot positions from free/total balances.

        ``avg_price`` is unknown for spot balances (exchanges don't store an
        entry cost) so we fall back to the current mark price as a best-effort
        substitute; callers that need true cost basis should use a separate
        position tracker that records order fills.
        """
        out: dict[str, Position] = {}
        for asset, amount in self._non_zero_totals().items():
            if asset == self.base_currency:
                continue
            symbol = f"{asset}/{self.base_currency}"
            price = self._safe_price(symbol)
            out[symbol] = Position(symbol=symbol, qty=amount, avg_price=price)
        return out

    def equity(self) -> float:
        equity = 0.0
        for asset, amount in self._non_zero_totals().items():
            if asset == self.base_currency:
                equity += amount
                continue
            price = self._safe_price(f"{asset}/{self.base_currency}")
            equity += amount * price
        return equity
