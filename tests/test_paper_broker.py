"""Paper broker unit tests."""
from src.execution.base import Order, OrderStatus, OrderType
from src.execution.paper_broker import PaperBroker


def test_market_buy_fills_and_updates_cash():
    b = PaperBroker(starting_cash=1_000.0)
    b.set_price("BTC/USDT", 100.0)
    o = b.submit(Order(symbol="BTC/USDT", side="buy", qty=2.0))
    assert o.status == OrderStatus.FILLED
    assert b.cash == 800.0
    assert b.positions()["BTC/USDT"].qty == 2.0


def test_buy_rejected_when_insufficient_cash():
    b = PaperBroker(starting_cash=100.0)
    b.set_price("BTC/USDT", 100.0)
    o = b.submit(Order(symbol="BTC/USDT", side="buy", qty=2.0))
    assert o.status == OrderStatus.REJECTED


def test_sell_without_position_rejected():
    b = PaperBroker(starting_cash=1_000.0)
    b.set_price("BTC/USDT", 100.0)
    o = b.submit(Order(symbol="BTC/USDT", side="sell", qty=1.0))
    assert o.status == OrderStatus.REJECTED


def test_limit_buy_stays_pending_above_limit():
    b = PaperBroker(starting_cash=1_000.0)
    b.set_price("BTC/USDT", 105.0)
    o = b.submit(Order(symbol="BTC/USDT", side="buy", qty=1.0,
                       order_type=OrderType.LIMIT, limit_price=100.0))
    assert o.status == OrderStatus.PENDING


def test_equity_mark_to_market():
    b = PaperBroker(starting_cash=1_000.0)
    b.set_price("BTC/USDT", 100.0)
    b.submit(Order(symbol="BTC/USDT", side="buy", qty=2.0))
    b.set_price("BTC/USDT", 150.0)
    assert b.equity() == 800.0 + 2.0 * 150.0
