"""Abstract market data provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class Candle:
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class DataProvider(ABC):
    """Common interface for all market data sources."""

    name: str

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Return a DataFrame indexed by timestamp with OHLCV columns."""

    @abstractmethod
    def latest_price(self, symbol: str) -> float:
        """Return the latest traded price for `symbol`."""

    def stream(self, symbols: Iterable[str], timeframe: str):
        """Optional: yield live candles. Default raises NotImplementedError."""
        raise NotImplementedError(f"{self.name} does not implement streaming yet")
