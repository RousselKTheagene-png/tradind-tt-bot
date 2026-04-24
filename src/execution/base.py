"""Abstract broker/execution interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    symbol: str
    side: str                     # "buy" | "sell"
    qty: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    id: str = ""
    status: OrderStatus = OrderStatus.PENDING
    fill_price: float | None = None
    filled_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Broker(ABC):
    """Common interface for paper and live brokers."""

    @abstractmethod
    def submit(self, order: Order) -> Order: ...

    @abstractmethod
    def cancel(self, order_id: str) -> None: ...

    @abstractmethod
    def positions(self) -> dict[str, Position]: ...

    @abstractmethod
    def equity(self) -> float: ...
