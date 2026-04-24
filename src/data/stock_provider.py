"""US stock market data via Alpaca (alpaca-py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from .base import DataProvider

# Alpaca timeframe mapping. Expand as needed.
_TIMEFRAME_MAP = {
    "1m": ("Minute", 1),
    "5m": ("Minute", 5),
    "15m": ("Minute", 15),
    "30m": ("Minute", 30),
    "1h": ("Hour", 1),
    "1d": ("Day", 1),
}


class StockProvider(DataProvider):
    """Thin wrapper around alpaca-py's market data client."""

    name = "alpaca_stocks"

    def __init__(self, api_key: str = "", api_secret: str = ""):
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.trading.client import TradingClient  # for latest trade

        self._data = StockHistoricalDataClient(api_key, api_secret)
        self._trading = TradingClient(api_key, api_secret, paper=True)

    def _tf(self, timeframe: str):
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        unit_name, amount = _TIMEFRAME_MAP.get(timeframe, ("Hour", 1))
        return TimeFrame(amount, getattr(TimeFrameUnit, unit_name))

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest

        # Alpaca needs a start/end window; approximate by walking back enough bars.
        minutes_per_bar = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "1d": 60 * 24,
        }.get(timeframe, 60)
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes_per_bar * (limit + 10))

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=self._tf(timeframe),
            start=start,
            end=end,
            limit=limit,
        )
        bars = self._data.get_stock_bars(req).df
        if bars.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        # alpaca-py returns a multi-index (symbol, timestamp); flatten to timestamp.
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level=0)
        bars = bars.rename(columns={
            "open": "open", "high": "high", "low": "low",
            "close": "close", "volume": "volume",
        })
        return bars[["open", "high", "low", "close", "volume"]].tail(limit)

    def latest_price(self, symbol: str) -> float:
        from alpaca.data.requests import StockLatestTradeRequest

        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trades = self._data.get_stock_latest_trade(req)
        return float(trades[symbol].price)
