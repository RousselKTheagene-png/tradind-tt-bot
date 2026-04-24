"""Unit tests for the OANDA forex data provider and broker, using mocks."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Skip the whole module if the OANDA SDK isn't installed.
pytest.importorskip("oandapyV20")


def _fake_candles(n: int = 5) -> dict:
    candles = []
    for i in range(n):
        candles.append({
            "complete": True,
            "time": f"2024-01-01T{i:02d}:00:00.000000000Z",
            "volume": 100 + i,
            "mid": {"o": f"1.100{i}", "h": f"1.101{i}",
                    "l": f"1.099{i}", "c": f"1.1005"},
        })
    # A non-complete candle should be dropped.
    candles.append({
        "complete": False, "time": "2024-01-02T00:00:00.000000000Z",
        "volume": 0, "mid": {"o": "1.2", "h": "1.2", "l": "1.2", "c": "1.2"},
    })
    return {"instrument": "EUR_USD", "granularity": "H1", "candles": candles}


def _install_request_side_effect(client: MagicMock, response: dict) -> None:
    """Make client.request(req) assign req.response = response."""
    def side_effect(req):
        req.response = response
        return response
    client.request.side_effect = side_effect


# --- ForexProvider ----------------------------------------------------------

def test_forex_provider_fetch_ohlcv_drops_incomplete_and_parses_mids():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client
        _install_request_side_effect(client, _fake_candles(5))

        from src.data.forex_provider import ForexProvider
        p = ForexProvider(api_key="k", account_id="a", environment="practice")
        df = p.fetch_ohlcv("EUR_USD", "1h", limit=10)

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        # 5 complete + 1 incomplete, incomplete dropped
        assert len(df) == 5
        assert isinstance(df.index, pd.DatetimeIndex)
        # Types are floats
        assert df["close"].dtype == float
        assert df["open"].iloc[0] == pytest.approx(1.1000)


def test_forex_provider_fetch_ohlcv_empty_returns_empty_frame():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client
        _install_request_side_effect(client, {"candles": []})

        from src.data.forex_provider import ForexProvider
        p = ForexProvider(api_key="k", account_id="a")
        df = p.fetch_ohlcv("EUR_USD", "1h", limit=10)
        assert df.empty
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_forex_provider_latest_price_midpoint():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client
        _install_request_side_effect(client, {"prices": [{
            "instrument": "EUR_USD",
            "bids": [{"price": "1.1000"}],
            "asks": [{"price": "1.1002"}],
        }]})

        from src.data.forex_provider import ForexProvider
        p = ForexProvider(api_key="k", account_id="a")
        assert p.latest_price("EUR_USD") == pytest.approx(1.1001)


def test_forex_provider_rejects_bad_environment():
    with patch("oandapyV20.API"):
        from src.data.forex_provider import ForexProvider
        with pytest.raises(ValueError):
            ForexProvider(api_key="k", account_id="a", environment="demo")


# --- OandaBroker ------------------------------------------------------------

def test_oanda_broker_submits_market_order_buy():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client
        _install_request_side_effect(client, {
            "orderCreateTransaction": {"id": "100", "instrument": "EUR_USD"},
            "orderFillTransaction": {"id": "101", "price": "1.1005", "units": "1000"},
            "lastTransactionID": "101",
        })

        from src.execution.oanda_broker import OandaBroker
        from src.execution.base import Order, OrderStatus

        broker = OandaBroker(api_key="k", account_id="a", environment="practice")
        result = broker.submit(Order(symbol="EUR_USD", side="buy", qty=1000))

        assert result.id == "100"
        assert result.status == OrderStatus.FILLED
        assert result.fill_price == pytest.approx(1.1005)
        client.request.assert_called_once()


def test_oanda_broker_rejects_on_exception():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client
        client.request.side_effect = RuntimeError("market halted")

        from src.execution.oanda_broker import OandaBroker
        from src.execution.base import Order, OrderStatus

        broker = OandaBroker(api_key="k", account_id="a")
        result = broker.submit(Order(symbol="EUR_USD", side="sell", qty=500))
        assert result.status == OrderStatus.REJECTED
        assert "halted" in result.metadata.get("error", "")


def test_oanda_broker_pending_when_no_fill_transaction():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client
        _install_request_side_effect(client, {
            "orderCreateTransaction": {"id": "200"},
            "lastTransactionID": "200",
        })

        from src.execution.oanda_broker import OandaBroker
        from src.execution.base import Order, OrderStatus

        broker = OandaBroker(api_key="k", account_id="a")
        result = broker.submit(Order(symbol="EUR_USD", side="buy", qty=1000))
        assert result.status == OrderStatus.PENDING
        assert result.fill_price is None


def test_oanda_broker_positions_long_and_short():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client
        _install_request_side_effect(client, {"positions": [
            {"instrument": "EUR_USD",
             "long":  {"units": "1000", "averagePrice": "1.1000"},
             "short": {"units": "0",    "averagePrice": "0"}},
            {"instrument": "USD_JPY",
             "long":  {"units": "0",     "averagePrice": "0"},
             "short": {"units": "-500",  "averagePrice": "150.25"}},
            {"instrument": "GBP_USD",  # flat on both sides - should be skipped
             "long":  {"units": "0",     "averagePrice": "0"},
             "short": {"units": "0",     "averagePrice": "0"}},
        ]})

        from src.execution.oanda_broker import OandaBroker
        broker = OandaBroker(api_key="k", account_id="a")
        positions = broker.positions()

        assert set(positions.keys()) == {"EUR_USD", "USD_JPY"}
        assert positions["EUR_USD"].qty == 1000.0
        assert positions["EUR_USD"].avg_price == pytest.approx(1.1000)
        assert positions["USD_JPY"].qty == -500.0
        assert positions["USD_JPY"].avg_price == pytest.approx(150.25)


def test_oanda_broker_equity_uses_nav():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client
        _install_request_side_effect(client, {"account": {"balance": "10000.0",
                                                          "NAV": "10123.45"}})

        from src.execution.oanda_broker import OandaBroker
        broker = OandaBroker(api_key="k", account_id="a")
        assert broker.equity() == pytest.approx(10123.45)


def test_oanda_broker_rejects_zero_qty():
    with patch("oandapyV20.API") as api_cls:
        client = MagicMock()
        api_cls.return_value = client

        from src.execution.oanda_broker import OandaBroker
        from src.execution.base import Order, OrderStatus

        broker = OandaBroker(api_key="k", account_id="a")
        result = broker.submit(Order(symbol="EUR_USD", side="buy", qty=0.4))
        # qty rounds to 0 units -> ValueError -> REJECTED
        assert result.status == OrderStatus.REJECTED
