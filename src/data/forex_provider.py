"""Forex market data via OANDA v20 REST API (oandapyV20)."""
from __future__ import annotations

import pandas as pd

from .base import DataProvider

# OANDA granularity mapping. Expand as needed.
_GRANULARITY_MAP = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "H1",
    "4h": "H4",
    "1d": "D",
    "1w": "W",
}


class ForexProvider(DataProvider):
    """Thin wrapper around oandapyV20's REST client for candles and pricing."""

    name = "oanda_forex"

    def __init__(self, api_key: str = "", account_id: str = "",
                 environment: str = "practice"):
        from oandapyV20 import API  # lazy import

        if environment not in {"practice", "live"}:
            raise ValueError("environment must be 'practice' or 'live'")
        self.account_id = account_id
        self.environment = environment
        self.client = API(access_token=api_key, environment=environment)

    def _granularity(self, timeframe: str) -> str:
        return _GRANULARITY_MAP.get(timeframe, "H1")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        import oandapyV20.endpoints.instruments as instruments

        params = {"granularity": self._granularity(timeframe),
                  "count": min(max(int(limit), 1), 5000),
                  "price": "M"}
        req = instruments.InstrumentsCandles(instrument=symbol, params=params)
        self.client.request(req)
        candles = req.response.get("candles", [])

        rows = []
        for c in candles:
            if not c.get("complete", False):
                continue
            mid = c.get("mid", {})
            rows.append({
                "timestamp": pd.to_datetime(c["time"], utc=True),
                "open": float(mid["o"]),
                "high": float(mid["h"]),
                "low": float(mid["l"]),
                "close": float(mid["c"]),
                "volume": float(c.get("volume", 0)),
            })

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return pd.DataFrame(rows).set_index("timestamp")[
            ["open", "high", "low", "close", "volume"]
        ]

    def latest_price(self, symbol: str) -> float:
        import oandapyV20.endpoints.pricing as pricing

        req = pricing.PricingInfo(accountID=self.account_id,
                                  params={"instruments": symbol})
        self.client.request(req)
        prices = req.response.get("prices", [])
        if not prices:
            raise RuntimeError(f"No pricing info returned for {symbol}")
        p = prices[0]
        bid = float(p["bids"][0]["price"])
        ask = float(p["asks"][0]["price"])
        return (bid + ask) / 2.0
