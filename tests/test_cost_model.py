"""Fee/slippage model and PaperBroker integration tests."""
import pytest

from src.execution.base import Order, OrderStatus
from src.execution.cost_model import CostModel
from src.execution.paper_broker import PaperBroker


def test_cost_model_defaults_are_zero():
    cm = CostModel()
    assert cm.apply_slippage(100.0, "buy") == 100.0
    assert cm.apply_slippage(100.0, "sell") == 100.0
    assert cm.fee(100.0, 1.0) == 0.0


def test_slippage_raises_buy_price_and_lowers_sell_price():
    cm = CostModel(slippage_bps=10)  # 10 bps = 0.10%
    assert cm.apply_slippage(100.0, "buy") == pytest.approx(100.10)
    assert cm.apply_slippage(100.0, "sell") == pytest.approx(99.90)


def test_fee_is_proportional_to_notional():
    cm = CostModel(fee_bps=25)  # 25 bps = 0.25%
    assert cm.fee(100.0, 4.0) == pytest.approx(1.0)  # 400 * 0.0025 = 1.0


def test_paper_broker_with_no_cost_matches_legacy_behavior():
    b = PaperBroker(starting_cash=1_000.0)
    b.set_price("BTC/USDT", 100.0)
    o = b.submit(Order(symbol="BTC/USDT", side="buy", qty=2.0))
    assert o.status == OrderStatus.FILLED
    assert b.cash == 800.0
    assert b.total_fees_paid == 0.0


def test_paper_broker_applies_slippage_on_buy():
    cm = CostModel(slippage_bps=50)  # 0.5%
    b = PaperBroker(starting_cash=1_000.0, cost_model=cm)
    b.set_price("BTC/USDT", 100.0)
    o = b.submit(Order(symbol="BTC/USDT", side="buy", qty=1.0))
    assert o.status == OrderStatus.FILLED
    assert o.fill_price == pytest.approx(100.5)
    assert b.cash == pytest.approx(1_000.0 - 100.5)


def test_paper_broker_applies_fee_on_buy_and_sell():
    cm = CostModel(fee_bps=100)  # 1% fee
    b = PaperBroker(starting_cash=1_000.0, cost_model=cm)
    b.set_price("BTC/USDT", 100.0)
    buy = b.submit(Order(symbol="BTC/USDT", side="buy", qty=1.0))
    # buy costs 100 + 1 (fee) = 101
    assert b.cash == pytest.approx(899.0)
    assert buy.metadata["fee"] == pytest.approx(1.0)

    sell = b.submit(Order(symbol="BTC/USDT", side="sell", qty=1.0))
    # sell credits 100 - 1 (fee) = 99 -> cash back to 998
    assert b.cash == pytest.approx(998.0)
    assert sell.metadata["fee"] == pytest.approx(1.0)
    assert b.total_fees_paid == pytest.approx(2.0)


def test_paper_broker_rejects_buy_when_fee_pushes_over_cash():
    cm = CostModel(fee_bps=100)  # 1% fee
    b = PaperBroker(starting_cash=100.5, cost_model=cm)  # barely enough for price but not fee
    b.set_price("BTC/USDT", 100.0)
    o = b.submit(Order(symbol="BTC/USDT", side="buy", qty=1.0))
    assert o.status == OrderStatus.REJECTED
