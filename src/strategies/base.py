"""Abstract strategy interface and shared types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


@dataclass
class Signal:
    symbol: str
    side: Side
    strength: float          # 0..1 confidence
    price: float
    reason: str
    metadata: dict[str, Any]


class Strategy(ABC):
    """Base class for all strategies.

    Subclasses may override ``tolerated_regimes`` (a set of ``Regime`` values,
    imported lazily to avoid a cycle) to tell the execution layer which market
    conditions they are safe to trade in. An empty/None value means "all".
    """

    name: str
    tolerated_regimes: frozenset[str] | None = None

    def __init__(self, **params: Any):
        self.params = params

    @abstractmethod
    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        """Return a Signal or None if no action."""

    def accepts_regime(self, regime: str) -> bool:
        """Return True if this strategy is allowed to fire in ``regime``."""
        if not self.tolerated_regimes:
            return True
        return regime in self.tolerated_regimes
