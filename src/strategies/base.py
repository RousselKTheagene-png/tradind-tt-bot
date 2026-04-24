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
    """Base class for all strategies."""

    name: str

    def __init__(self, **params: Any):
        self.params = params

    @abstractmethod
    def generate_signal(self, symbol: str, ohlcv: pd.DataFrame) -> Signal | None:
        """Return a Signal or None if no action."""
