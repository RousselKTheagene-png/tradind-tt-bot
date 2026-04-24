"""Unit tests for the Alpaca data provider and broker, using mocks."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Skip the whole module if the Alpaca SDK isn't installed.
pytest.importorskip("alpaca")


# --- StockProvider ------------------------------------------------------------

def _fake_bars_df(symbol: str, n: int = 5) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [[symbol], pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")],
        names=["symbol", "timestamp"],
    )
    return pd.DataFrame({
        "open": range(n), "high": range(n), "low": range(n),
        "close": range(n), "volume": [100] * n, "trade_count": [1] * n, "vwap": range(n),
    }, index=idx)


def test_stock_provider_fetch_ohlcv_flattens_multiindex():
    with patch("alpaca.data.historical.StockHistoricalDataClient") as data_cls, \
         patch("alpaca.trading.client.TradingClient"):
        data_client = MagicMock()
        data_cls.return_value = data_client
        bars_obj = SimpleNamespace(df=_fake_bars_df("AAPL", 5))
        data_client.get_stock_bars.return_value = bars_obj

        from src.data.stock_provider import StockProvider
        p = StockProvider(api_key="k", api_secret="s")
        df = p.fetch_ohlcv("AAPL", "1h", limit=5)

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 5
        # Index should no longer be a MultiIndex.
        assert not isinstance(df.index, pd.MultiIndex)


def test_stock_provider_latest_price():
    with patch("alpaca.data.historical.StockHistoricalDataClient") as data_cls, \
         patch("alpaca.trading.client.TradingClient"):
        data_client = MagicMock()
        data_cls.return_value = data_client
        data_client.get_stock_latest_trade.return_value = {
            "AAPL": SimpleNamespace(price=189.42),
        }
        from src.data.stock_provider import StockProvider
        p = StockProvider(api_key="k", api_secret="s")
        assert p.latest_price("AAPL") == pytest.approx(189.42)


# --- AlpacaBroker -------------------------------------------------------------

def test_alpaca_broker_submits_market_order():
    with patch("alpaca.trading.client.TradingClient") as cls:
        client = MagicMock()
        cls.return_value = client
        client.submit_order.return_value = SimpleNamespace(
            id="abc-123", status="filled", filled_avg_price=150.0,
        )

        from src.execution.alpaca_broker import AlpacaBroker
        from src.execution.base import Order, OrderStatus

        broker = AlpacaBroker(api_key="k", api_secret="s", paper=True)
        result = broker.submit(Order(symbol="AAPL", side="buy", qty=1.0))

        assert result.id == "abc-123"
        assert result.status == OrderStatus.FILLED
        assert result.fill_price == 150.0
        client.submit_order.assert_called_once()


def test_alpaca_broker_rejects_on_exception():
    with patch("alpaca.trading.client.TradingClient") as cls:
        client = MagicMock()
        cls.return_value = client
        client.submit_order.side_effect = RuntimeError("insufficient buying power")

        from src.execution.alpaca_broker import AlpacaBroker
        from src.execution.base import Order, OrderStatus

        broker = AlpacaBroker(api_key="k", api_secret="s")
        result = broker.submit(Order(symbol="AAPL", side="buy", qty=1.0))
        assert result.status == OrderStatus.REJECTED
        assert "insufficient" in result.metadata.get("error", "")


def test_alpaca_broker_positions_and_equity():
    with patch("alpaca.trading.client.TradingClient") as cls:
        client = MagicMock()
        cls.return_value = client
        client.get_all_positions.return_value = [
            SimpleNamespace(symbol="AAPL", qty="10", avg_entry_price="150.0"),
            SimpleNamespace(symbol="NVDA", qty="5",  avg_entry_price="800.0"),
        ]
        client.get_account.return_value = SimpleNamespace(equity="25000.0")

        from src.execution.alpaca_broker import AlpacaBroker
        broker = AlpacaBroker(api_key="k", api_secret="s")
        positions = broker.positions()
        assert set(positions.keys()) == {"AAPL", "NVDA"}
        assert positions["AAPL"].qty == 10.0
        assert positions["NVDA"].avg_price == 800.0
        assert broker.equity() == 25_000.0
