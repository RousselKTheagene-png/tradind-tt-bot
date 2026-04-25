"""Main entry point. Wires data -> strategies -> risk -> execution -> journal."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .execution.base import Broker, Order, OrderType
from .execution.paper_broker import PaperBroker
from .execution.safety import ensure_live_safety
from .intelligence.regime import RegimeClassifier
from .monitoring.logger import configure_logging
from .monitoring.notifier import build_notifier
from .monitoring.sqlite_journal import open_journal
from .risk.risk_manager import RiskLimits, RiskManager
from .strategies.base import Side, Strategy
from .strategies.bollinger_squeeze import BollingerSqueeze
from .strategies.donchian_breakout import DonchianBreakout
from .strategies.ema_crossover import EmaCrossover
from .strategies.macd_divergence import MacdDivergence
from .strategies.rsi_reversion import RsiReversion
from .strategies.supertrend import Supertrend

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "ema_crossover": EmaCrossover,
    "rsi_reversion": RsiReversion,
    "bollinger_squeeze": BollingerSqueeze,
    "macd_divergence": MacdDivergence,
    "donchian_breakout": DonchianBreakout,
    "supertrend": Supertrend,
}


def load_config(path: str | Path) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def build_strategies(cfg: dict) -> list[Strategy]:
    out: list[Strategy] = []
    for entry in cfg.get("strategies", []):
        if not entry.get("enabled", True):
            continue
        klass = STRATEGY_REGISTRY.get(entry["name"])
        if klass is None:
            continue
        out.append(klass(**entry.get("params", {})))
    return out


def _use_live_broker(mode: str, market_cfg: dict) -> bool:
    """In ``live`` mode we route to a real broker adapter; otherwise PaperBroker.

    A market can still opt out of live routing by setting ``paper: true``.
    """
    if mode != "live":
        return False
    return bool(market_cfg.get("paper", True) is False)


def build_markets(cfg: dict, mode: str = "paper",
                  paper_starting_cash: float = 10_000.0) -> list[dict]:
    """Return a list of {name, provider, broker, symbols, timeframe} dicts.

    Each enabled market is paired with its own broker so order routing is
    per-market. In ``paper`` mode every market uses a ``PaperBroker``. In
    ``live`` mode, markets with ``paper: false`` in their config use the real
    adapter (Alpaca for stocks, OANDA for forex); unsupported live markets
    (crypto today) fall back to ``PaperBroker``.
    """
    markets: list[dict] = []

    crypto_cfg = cfg["markets"].get("crypto", {})
    if crypto_cfg.get("enabled"):
        from .data.crypto_provider import CryptoProvider
        exch = crypto_cfg.get("exchange", "binance")
        key_env = f"{exch.upper()}_API_KEY"
        secret_env = f"{exch.upper()}_API_SECRET"
        provider = CryptoProvider(
            exchange=exch,
            api_key=os.getenv(key_env, ""),
            api_secret=os.getenv(secret_env, ""),
        )
        if _use_live_broker(mode, crypto_cfg):
            from .execution.ccxt_broker import CcxtBroker
            broker: Broker = CcxtBroker(
                exchange=exch,
                api_key=os.getenv(key_env, ""),
                api_secret=os.getenv(secret_env, ""),
                base_currency=crypto_cfg.get("base_currency", "USDT"),
            )
        else:
            broker = PaperBroker(starting_cash=paper_starting_cash)
        markets.append({
            "name": "crypto",
            "provider": provider,
            "broker": broker,
            "symbols": crypto_cfg["symbols"],
            "timeframe": crypto_cfg.get("timeframe", "1h"),
        })

    stock_cfg = cfg["markets"].get("stocks", {})
    if stock_cfg.get("enabled"):
        from .data.stock_provider import StockProvider
        provider = StockProvider(
            api_key=os.getenv("ALPACA_API_KEY", ""),
            api_secret=os.getenv("ALPACA_API_SECRET", ""),
        )
        if _use_live_broker(mode, stock_cfg):
            from .execution.alpaca_broker import AlpacaBroker
            broker: Broker = AlpacaBroker(
                api_key=os.getenv("ALPACA_API_KEY", ""),
                api_secret=os.getenv("ALPACA_API_SECRET", ""),
                paper=stock_cfg.get("paper", True),
            )
        else:
            broker = PaperBroker(starting_cash=paper_starting_cash)
        markets.append({
            "name": "stocks",
            "provider": provider,
            "broker": broker,
            "symbols": stock_cfg["symbols"],
            "timeframe": stock_cfg.get("timeframe", "15m"),
        })

    forex_cfg = cfg["markets"].get("forex", {})
    if forex_cfg.get("enabled"):
        from .data.forex_provider import ForexProvider
        provider = ForexProvider(
            api_key=os.getenv("OANDA_API_KEY", ""),
            account_id=os.getenv("OANDA_ACCOUNT_ID", ""),
            environment=forex_cfg.get("environment", "practice"),
        )
        if _use_live_broker(mode, forex_cfg):
            from .execution.oanda_broker import OandaBroker
            broker = OandaBroker(
                api_key=os.getenv("OANDA_API_KEY", ""),
                account_id=os.getenv("OANDA_ACCOUNT_ID", ""),
                environment=forex_cfg.get("environment", "practice"),
            )
        else:
            broker = PaperBroker(starting_cash=paper_starting_cash)
        markets.append({
            "name": "forex",
            "provider": provider,
            "broker": broker,
            "symbols": forex_cfg["symbols"],
            "timeframe": forex_cfg.get("timeframe", "15m"),
        })

    return markets


def _total_equity(markets: list[dict]) -> float:
    """Sum equity across every market's broker."""
    total = 0.0
    for m in markets:
        try:
            total += float(m["broker"].equity())
        except Exception:
            continue
    return total


def run(cfg: dict, mode: str, markets: list[dict] | None = None,
        loop_forever: bool = True) -> None:
    log = configure_logging(cfg["monitoring"]["log_level"])
    journal = open_journal(cfg["monitoring"]["journal_path"])
    notifier = build_notifier(cfg)

    strategies = build_strategies(cfg)
    if markets is None:
        markets = build_markets(cfg, mode=mode)
    interval = cfg.get("loop_interval_seconds", 60)

    regime_cfg = cfg.get("regime", {})
    regime_filter: RegimeClassifier | None = None
    if regime_cfg.get("enabled", True):
        regime_filter = RegimeClassifier(
            method=regime_cfg.get("method", "rules"),
            adx_threshold=regime_cfg.get("adx_threshold", 25.0),
        )

    if not markets:
        raise SystemExit("No markets enabled in config.")

    starting_equity = _total_equity(markets)
    risk = RiskManager(starting_equity=starting_equity,
                       limits=RiskLimits(**cfg["risk"]))

    active = [(m["name"], m["symbols"], type(m["broker"]).__name__) for m in markets]
    log.info(f"Starting bot in {mode} mode with {len(strategies)} strategies on {active}")
    journal.record("start", {"mode": mode, "markets": active})

    while True:
        try:
            for market in markets:
                provider = market["provider"]
                broker: Broker = market["broker"]
                timeframe = market["timeframe"]
                for symbol in market["symbols"]:
                    ohlcv = provider.fetch_ohlcv(symbol, timeframe, limit=200)
                    last = float(ohlcv["close"].iloc[-1])
                    if isinstance(broker, PaperBroker):
                        broker.set_price(symbol, last)

                    current_regime = regime_filter.classify(ohlcv).value if regime_filter else None
                    journal.record("regime_snapshot", {
                        "market": market["name"], "symbol": symbol,
                        "regime": current_regime, "price": last,
                    })
                    notifier.on_regime_snapshot(market["name"], symbol, current_regime)

                    for strat in strategies:
                        sig = strat.generate_signal(symbol, ohlcv)
                        if sig is None or sig.side == Side.FLAT:
                            continue

                        if current_regime is not None and not strat.accepts_regime(current_regime):
                            log.info(f"{symbol} {strat.name} skipped in regime={current_regime}")
                            journal.record("regime_block", {
                                "symbol": symbol, "strategy": strat.name,
                                "regime": current_regime, "side": sig.side.value,
                            })
                            continue

                        equity = _total_equity(markets)
                        ok, reason = risk.can_open(equity)
                        if not ok:
                            log.warning(f"{symbol} {strat.name} blocked: {reason}")
                            journal.record("blocked", {"symbol": symbol, "reason": reason})
                            notifier.on_risk_block(symbol, reason)
                            continue

                        stop, take = risk.default_stop_take(sig.price, sig.side.value)
                        qty = risk.position_size(equity, sig.price, stop)
                        if qty <= 0:
                            continue

                        order = Order(symbol=symbol, side=sig.side.value, qty=qty,
                                      order_type=OrderType.MARKET,
                                      stop_loss=stop, take_profit=take,
                                      metadata={"strategy": strat.name, "market": market["name"],
                                                "reason": sig.reason})
                        filled = broker.submit(order)
                        log.info(f"Submitted {filled.side} {filled.qty:.6f} {symbol} @ {filled.fill_price} "
                                 f"via {type(broker).__name__}")
                        order_payload = {
                            "id": filled.id, "symbol": symbol, "side": filled.side,
                            "qty": filled.qty, "fill_price": filled.fill_price,
                            "status": filled.status.value, "strategy": strat.name,
                            "market": market["name"], "broker": type(broker).__name__,
                        }
                        journal.record("order", order_payload)
                        notifier.on_order(order_payload)
                        if filled.fill_price is not None:
                            risk.on_fill(_total_equity(markets))

            journal.record("equity_snapshot", {
                "equity": _total_equity(markets),
                "brokers": [
                    {"market": m["name"], "broker": type(m["broker"]).__name__,
                     "equity": float(m["broker"].equity())}
                    for m in markets
                ],
            })
        except Exception as exc:  # don't crash the loop
            log.exception(f"Loop error: {exc}")
            journal.record("error", {"error": str(exc)})
            notifier.on_error(str(exc))

        if not loop_forever:
            break
        time.sleep(interval)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Multi-market trading bot")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg["mode"] = args.mode
    ensure_live_safety(cfg)
    run(cfg, mode=args.mode)


if __name__ == "__main__":
    main()
