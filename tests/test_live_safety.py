"""Tests for live-mode broker wiring and real-money safety gates."""
from unittest.mock import MagicMock, patch

import pytest


# --- ensure_live_safety -----------------------------------------------------

def test_safety_paper_mode_is_noop():
    from src.execution.safety import ensure_live_safety
    cfg = {"mode": "paper", "markets": {"stocks": {"enabled": True, "paper": False}}}
    ensure_live_safety(cfg)  # no raise


def test_safety_live_mode_all_paper_is_noop():
    from src.execution.safety import ensure_live_safety
    cfg = {"mode": "live", "markets": {
        "stocks": {"enabled": True, "paper": True},
        "forex":  {"enabled": True, "paper": True, "environment": "practice"},
    }}
    ensure_live_safety(cfg)  # no raise


def test_safety_live_mode_practice_environment_is_noop():
    from src.execution.safety import ensure_live_safety
    cfg = {"mode": "live", "markets": {
        "forex": {"enabled": True, "paper": False, "environment": "practice"},
    }}
    ensure_live_safety(cfg)  # practice endpoint is allowed


def test_safety_real_money_blocked_without_env(monkeypatch):
    from src.execution.safety import ensure_live_safety, ENV_VAR
    monkeypatch.delenv(ENV_VAR, raising=False)
    cfg = {"mode": "live",
           "live_safety": {"real_money_confirmed": True},
           "markets": {"stocks": {"enabled": True, "paper": False}}}
    with pytest.raises(SystemExit, match="safety gates"):
        ensure_live_safety(cfg)


def test_safety_real_money_blocked_without_config_flag(monkeypatch):
    from src.execution.safety import ensure_live_safety, ENV_VAR, ENV_EXPECTED
    monkeypatch.setenv(ENV_VAR, ENV_EXPECTED)
    cfg = {"mode": "live",
           "live_safety": {"real_money_confirmed": False},
           "markets": {"stocks": {"enabled": True, "paper": False}}}
    with pytest.raises(SystemExit, match="safety gates"):
        ensure_live_safety(cfg)


def test_safety_real_money_allowed_when_both_gates_set(monkeypatch):
    from src.execution.safety import ensure_live_safety, ENV_VAR, ENV_EXPECTED
    monkeypatch.setenv(ENV_VAR, ENV_EXPECTED)
    cfg = {"mode": "live",
           "live_safety": {"real_money_confirmed": True},
           "markets": {"stocks": {"enabled": True, "paper": False},
                       "forex":  {"enabled": True, "paper": False,
                                  "environment": "live"}}}
    ensure_live_safety(cfg)  # no raise


def test_safety_wrong_env_value_blocked(monkeypatch):
    from src.execution.safety import ensure_live_safety, ENV_VAR
    monkeypatch.setenv(ENV_VAR, "YES")
    cfg = {"mode": "live",
           "live_safety": {"real_money_confirmed": True},
           "markets": {"stocks": {"enabled": True, "paper": False}}}
    with pytest.raises(SystemExit):
        ensure_live_safety(cfg)


# --- build_markets broker selection -----------------------------------------

def _base_cfg(**markets):
    return {"markets": markets}


def test_build_markets_paper_mode_uses_paper_broker_everywhere():
    from src.main import build_markets
    from src.execution.paper_broker import PaperBroker

    cfg = _base_cfg(
        crypto={"enabled": True, "exchange": "kraken", "paper": False,
                "symbols": ["BTC/USDT"], "timeframe": "1h"},
    )
    with patch("ccxt.kraken") as kraken_cls:
        kraken_cls.return_value = MagicMock()
        markets = build_markets(cfg, mode="paper")

    assert len(markets) == 1
    assert isinstance(markets[0]["broker"], PaperBroker)


def test_build_markets_live_mode_stocks_paper_true_uses_paper_broker():
    pytest.importorskip("alpaca")
    from src.main import build_markets
    from src.execution.paper_broker import PaperBroker

    cfg = _base_cfg(
        stocks={"enabled": True, "paper": True,
                "symbols": ["SPY"], "timeframe": "15m"},
    )
    with patch("alpaca.data.historical.StockHistoricalDataClient"), \
         patch("alpaca.trading.client.TradingClient"):
        markets = build_markets(cfg, mode="live")

    assert len(markets) == 1
    assert isinstance(markets[0]["broker"], PaperBroker)


def test_build_markets_live_mode_stocks_paper_false_uses_alpaca_broker():
    pytest.importorskip("alpaca")
    from src.main import build_markets
    from src.execution.alpaca_broker import AlpacaBroker

    cfg = _base_cfg(
        stocks={"enabled": True, "paper": False,
                "symbols": ["SPY"], "timeframe": "15m"},
    )
    with patch("alpaca.data.historical.StockHistoricalDataClient"), \
         patch("alpaca.trading.client.TradingClient") as trading_cls:
        trading_cls.return_value = MagicMock()
        markets = build_markets(cfg, mode="live")

    assert len(markets) == 1
    assert isinstance(markets[0]["broker"], AlpacaBroker)
    # paper flag forwarded to the adapter
    assert markets[0]["broker"].paper is False


def test_build_markets_live_mode_forex_paper_false_uses_oanda_broker():
    pytest.importorskip("oandapyV20")
    from src.main import build_markets
    from src.execution.oanda_broker import OandaBroker

    cfg = _base_cfg(
        forex={"enabled": True, "paper": False, "environment": "practice",
               "symbols": ["EUR_USD"], "timeframe": "15m"},
    )
    with patch("oandapyV20.API") as api_cls:
        api_cls.return_value = MagicMock()
        markets = build_markets(cfg, mode="live")

    assert len(markets) == 1
    assert isinstance(markets[0]["broker"], OandaBroker)


# --- run() dispatches to per-market broker ----------------------------------

def test_run_dispatches_orders_to_market_broker(tmp_path):
    """run() should submit orders via the broker attached to each market."""
    import pandas as pd
    from src.execution.base import Order, OrderStatus
    from src.strategies.base import Side, Signal, Strategy
    from src.main import run, STRATEGY_REGISTRY

    class AlwaysBuy(Strategy):
        name = "always_buy"
        tolerated_regimes = frozenset({"trending_up", "trending_down",
                                       "ranging", "high_volatility", "unknown"})

        def generate_signal(self, symbol, ohlcv):
            price = float(ohlcv["close"].iloc[-1])
            return Signal(symbol, Side.BUY, 0.9, price, "test", {})

    idx = pd.date_range("2024-01-01", periods=60, freq="1h", tz="UTC")
    close = [100.0] * 60
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": [1_000] * 60}, index=idx)

    provider = MagicMock()
    provider.fetch_ohlcv.return_value = df

    broker = MagicMock()
    broker.equity.return_value = 10_000.0
    broker.positions.return_value = {}

    def _submit(order: Order) -> Order:
        order.id = "xyz"
        order.status = OrderStatus.FILLED
        order.fill_price = 100.0
        return order
    broker.submit.side_effect = _submit

    markets = [{"name": "stocks", "provider": provider, "broker": broker,
                "symbols": ["SPY"], "timeframe": "15m"}]

    cfg = {
        "monitoring": {"log_level": "ERROR",
                       "journal_path": str(tmp_path / "journal.jsonl")},
        "risk": {"max_risk_per_trade_pct": 1.0, "max_daily_loss_pct": 3.0,
                 "max_open_positions": 5, "max_drawdown_pct": 15.0,
                 "default_stop_loss_pct": 2.0, "default_take_profit_pct": 4.0},
        "regime": {"enabled": False},
        "strategies": [{"name": "always_buy", "enabled": True, "params": {}}],
    }

    STRATEGY_REGISTRY["always_buy"] = AlwaysBuy
    try:
        run(cfg, mode="live", markets=markets, loop_forever=False)
    finally:
        STRATEGY_REGISTRY.pop("always_buy", None)

    assert broker.submit.called, "per-market broker was not invoked"
    submitted = broker.submit.call_args.args[0]
    assert submitted.symbol == "SPY"
    assert submitted.side == "buy"
