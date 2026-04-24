"""Tests for the CCXT live crypto broker adapter."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from src.execution.base import Order, OrderStatus, OrderType


def _install_fake_ccxt(monkeypatch, client: MagicMock) -> None:
    """Install a stub ``ccxt`` module that returns ``client`` from
    ``ccxt.<name>(...)`` so CcxtBroker's lazy import picks it up."""
    fake = types.ModuleType("ccxt")
    factory = MagicMock(return_value=client)
    fake.binance = factory  # noqa: attribute via setattr below for mypy
    setattr(fake, "binance", factory)
    monkeypatch.setitem(sys.modules, "ccxt", fake)


def _make_broker(monkeypatch, client):
    _install_fake_ccxt(monkeypatch, client)
    from src.execution.ccxt_broker import CcxtBroker
    return CcxtBroker(exchange="binance", api_key="k", api_secret="s",
                      base_currency="USDT")


def test_submit_market_order_marks_filled(monkeypatch):
    client = MagicMock()
    client.create_order.return_value = {"id": "abc", "status": "closed",
                                        "average": 42_000.0}
    broker = _make_broker(monkeypatch, client)
    order = Order(symbol="BTC/USDT", side="buy", qty=0.1,
                  order_type=OrderType.MARKET)
    out = broker.submit(order)
    assert out.status == OrderStatus.FILLED
    assert out.id == "abc"
    assert out.fill_price == 42_000.0
    client.create_order.assert_called_once_with(
        symbol="BTC/USDT", type="market", side="buy", amount=0.1, price=None)


def test_submit_limit_order_passes_price(monkeypatch):
    client = MagicMock()
    client.create_order.return_value = {"id": "L1", "status": "open",
                                        "price": 41_500.0}
    broker = _make_broker(monkeypatch, client)
    order = Order(symbol="BTC/USDT", side="buy", qty=0.1,
                  order_type=OrderType.LIMIT, limit_price=41_500.0)
    out = broker.submit(order)
    assert out.status == OrderStatus.PENDING
    args = client.create_order.call_args.kwargs
    assert args["type"] == "limit" and args["price"] == 41_500.0


def test_submit_limit_without_price_rejected(monkeypatch):
    client = MagicMock()
    broker = _make_broker(monkeypatch, client)
    order = Order(symbol="BTC/USDT", side="buy", qty=0.1,
                  order_type=OrderType.LIMIT, limit_price=None)
    out = broker.submit(order)
    assert out.status == OrderStatus.REJECTED
    assert "error" in out.metadata
    client.create_order.assert_not_called()


def test_submit_maps_canceled_status(monkeypatch):
    client = MagicMock()
    client.create_order.return_value = {"id": "x", "status": "canceled"}
    broker = _make_broker(monkeypatch, client)
    out = broker.submit(Order(symbol="BTC/USDT", side="sell", qty=0.1))
    assert out.status == OrderStatus.CANCELLED


def test_submit_exchange_error_rejected(monkeypatch):
    client = MagicMock()
    client.create_order.side_effect = RuntimeError("insufficient funds")
    broker = _make_broker(monkeypatch, client)
    out = broker.submit(Order(symbol="BTC/USDT", side="buy", qty=0.1))
    assert out.status == OrderStatus.REJECTED
    assert "insufficient funds" in out.metadata["error"]


def test_cancel_delegates_to_client(monkeypatch):
    client = MagicMock()
    broker = _make_broker(monkeypatch, client)
    broker.cancel("order-1")
    client.cancel_order.assert_called_once_with("order-1")


def test_positions_skips_base_and_zero(monkeypatch):
    client = MagicMock()
    client.fetch_balance.return_value = {
        "total": {"USDT": 1_000.0, "BTC": 0.25, "ETH": 0, "SOL": None},
    }
    client.fetch_ticker.side_effect = lambda sym: {
        "BTC/USDT": {"last": 42_000.0},
    }[sym]
    broker = _make_broker(monkeypatch, client)
    pos = broker.positions()
    assert set(pos.keys()) == {"BTC/USDT"}
    assert pos["BTC/USDT"].qty == 0.25
    assert pos["BTC/USDT"].avg_price == 42_000.0


def test_equity_marks_holdings_to_market(monkeypatch):
    client = MagicMock()
    client.fetch_balance.return_value = {
        "total": {"USDT": 1_000.0, "BTC": 0.25, "ETH": 2.0},
    }
    prices = {"BTC/USDT": 40_000.0, "ETH/USDT": 2_500.0}
    client.fetch_ticker.side_effect = lambda sym: {"last": prices[sym]}
    broker = _make_broker(monkeypatch, client)
    eq = broker.equity()
    assert eq == pytest.approx(1_000.0 + 0.25 * 40_000.0 + 2.0 * 2_500.0)


def test_equity_skips_ticker_errors(monkeypatch):
    client = MagicMock()
    client.fetch_balance.return_value = {"total": {"USDT": 500.0, "WEIRD": 1.0}}
    client.fetch_ticker.side_effect = RuntimeError("no market")
    broker = _make_broker(monkeypatch, client)
    assert broker.equity() == 500.0


def test_build_markets_routes_crypto_live_to_ccxt(monkeypatch, tmp_path):
    """In live mode with paper:false, crypto market should use CcxtBroker."""
    client = MagicMock()
    _install_fake_ccxt(monkeypatch, client)

    from src.main import build_markets
    from src.execution.ccxt_broker import CcxtBroker

    cfg = {
        "markets": {
            "crypto": {"enabled": True, "exchange": "binance", "paper": False,
                       "base_currency": "USDT", "symbols": ["BTC/USDT"],
                       "timeframe": "1h"},
        },
    }
    monkeypatch.setenv("BINANCE_API_KEY", "k")
    monkeypatch.setenv("BINANCE_API_SECRET", "s")
    markets = build_markets(cfg, mode="live")
    assert len(markets) == 1
    assert markets[0]["name"] == "crypto"
    assert isinstance(markets[0]["broker"], CcxtBroker)


def test_build_markets_crypto_paper_stays_on_paper_broker(monkeypatch):
    from src.main import build_markets
    from src.execution.paper_broker import PaperBroker

    client = MagicMock()
    _install_fake_ccxt(monkeypatch, client)
    cfg = {"markets": {"crypto": {"enabled": True, "exchange": "binance",
                                  "paper": True, "symbols": ["BTC/USDT"],
                                  "timeframe": "1h"}}}
    markets = build_markets(cfg, mode="live")
    assert isinstance(markets[0]["broker"], PaperBroker)
