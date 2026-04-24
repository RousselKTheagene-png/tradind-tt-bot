"""Risk manager unit tests."""
from datetime import date

from src.risk.risk_manager import RiskLimits, RiskManager


def test_position_sizing_respects_risk_budget():
    rm = RiskManager(10_000.0, RiskLimits(max_risk_per_trade_pct=1.0))
    qty = rm.position_size(equity=10_000, entry=100.0, stop=95.0)
    # risk = 5 * qty == 100  ->  qty == 20
    assert abs(qty - 20.0) < 1e-9


def test_position_sizing_zero_when_no_distance():
    rm = RiskManager(10_000.0)
    assert rm.position_size(10_000, 100, 100) == 0.0


def test_can_open_blocks_when_too_many_positions():
    rm = RiskManager(10_000.0, RiskLimits(max_open_positions=1))
    rm.state.open_positions = 1
    ok, reason = rm.can_open(10_000.0)
    assert not ok and "max open" in reason


def test_can_open_blocks_on_daily_loss():
    rm = RiskManager(10_000.0, RiskLimits(max_daily_loss_pct=2.0))
    rm.state.realized_pnl_today = -300.0  # -3% on 10k
    ok, reason = rm.can_open(10_000.0)
    assert not ok and "daily loss" in reason


def test_default_stop_take_buy():
    rm = RiskManager(10_000.0,
                     RiskLimits(default_stop_loss_pct=2.0, default_take_profit_pct=4.0))
    stop, take = rm.default_stop_take(100.0, "buy")
    assert abs(stop - 98.0) < 1e-9
    assert abs(take - 104.0) < 1e-9


def test_roll_day_resets_daily_pnl():
    rm = RiskManager(10_000.0)
    rm.state.realized_pnl_today = -100.0
    rm.roll_day(date(2099, 1, 1))
    assert rm.state.realized_pnl_today == 0.0
