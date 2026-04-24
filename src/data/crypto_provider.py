"""Crypto market data via ccxt (Binance, Coinbase, etc.)."""
from __future__ import annotations

import pandas as pd

from .base import DataProvider


class CryptoProvider(DataProvider):
    """Thin wrapper around a ccxt exchange instance."""

    def __init__(self, exchange: str = "binance", api_key: str = "", api_secret: str = ""):
        import ccxt  # lazy import so tests can run without ccxt installed

        klass = getattr(ccxt, exchange)
        self.name = exchange
        self.client = klass({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        raw = self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.set_index("timestamp")

    def latest_price(self, symbol: str) -> float:
        ticker = self.client.fetch_ticker(symbol)
        return float(ticker["last"])
