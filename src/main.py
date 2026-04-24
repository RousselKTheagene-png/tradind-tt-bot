"""Main entry point. Wires data -> strategies -> risk -> execution -> journal."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .execution.base import Order, OrderType
from .execution.paper_broker import PaperBroker
from .intelligence.regime import RegimeClassifier
from .monitoring.journal import TradeJournal
from .monitoring.logger import configure_logging
from .risk.risk_manager import RiskLimits, RiskManager
from .strategies.base import Side, Strategy
from .strategies.bollinger_squeeze import BollingerSqueeze
from .strategies.donchian_breakout import DonchianBreakout
from .strategies.ema_crossover import EmaCrossover
from .strategies.macd_divergence import MacdDivergence
from .strategies.rsi_reversion import RsiReversion

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "ema_crossover": EmaCrossover,
    "rsi_reversion": RsiReversion,
    "bollinger_squeeze": BollingerSqueeze,
    "macd_divergence": MacdDivergence,
    "donchian_breakout": DonchianBreakout,
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


def build_markets(cfg: dict) -> list[dict]:
    """Return a list of {provider, symbols, timeframe, name} dicts for each enabled market."""
    markets: list[dict] = []

    crypto_cfg = cfg["markets"].get("crypto", {})
    if crypto_cfg.get("enabled"):
        from .data.crypto_provider import CryptoProvider
        markets.append({
            "name": "crypto",
            "provider": CryptoProvider(
                exchange=crypto_cfg.get("exchange", "binance"),
                api_key=os.getenv("BINANCE_API_KEY", ""),
                api_secret=os.getenv("BINANCE_API_SECRET", ""),
            ),
            "symbols": crypto_cfg["symbols"],
            "timeframe": crypto_cfg.get("timeframe", "1h"),
        })

    stock_cfg = cfg["markets"].get("stocks", {})
    if stock_cfg.get("enabled"):
        from .data.stock_provider import StockProvider
        markets.append({
            "name": "stocks",
            "provider": StockProvider(
                api_key=os.getenv("ALPACA_API_KEY", ""),
                api_secret=os.getenv("ALPACA_API_SECRET", ""),
            ),
            "symbols": stock_cfg["symbols"],
            "timeframe": stock_cfg.get("timeframe", "15m"),
        })

    forex_cfg = cfg["markets"].get("forex", {})
    if forex_cfg.get("enabled"):
        from .data.forex_provider import ForexProvider
        markets.append({
            "name": "forex",
            "provider": ForexProvider(
                api_key=os.getenv("OANDA_API_KEY", ""),
                account_id=os.getenv("OANDA_ACCOUNT_ID", ""),
                environment=forex_cfg.get("environment", "practice"),
            ),
            "symbols": forex_cfg["symbols"],
            "timeframe": forex_cfg.get("timeframe", "15m"),
        })

    return markets


def run(cfg: dict, mode: str) -> None:
    log = configure_logging(cfg["monitoring"]["log_level"])
    journal = TradeJournal(cfg["monitoring"]["journal_path"])

    broker = PaperBroker(starting_cash=10_000.0)
    risk = RiskManager(starting_equity=broker.equity(),
                       limits=RiskLimits(**cfg["risk"]))
    strategies = build_strategies(cfg)
    markets = build_markets(cfg)
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

    active = [(m["name"], m["symbols"]) for m in markets]
    log.info(f"Starting bot in {mode} mode with {len(strategies)} strategies on {active}")
    journal.record("start", {"mode": mode, "markets": active})

    while True:
        try:
            for market in markets:
                provider = market["provider"]
                timeframe = market["timeframe"]
                for symbol in market["symbols"]:
                    ohlcv = provider.fetch_ohlcv(symbol, timeframe, limit=200)
                    last = float(ohlcv["close"].iloc[-1])
                    broker.set_price(symbol, last)

                    current_regime = regime_filter.classify(ohlcv).value if regime_filter else None

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

                        ok, reason = risk.can_open(broker.equity())
                        if not ok:
                            log.warning(f"{symbol} {strat.name} blocked: {reason}")
                            journal.record("blocked", {"symbol": symbol, "reason": reason})
                            continue

                        stop, take = risk.default_stop_take(sig.price, sig.side.value)
                        qty = risk.position_size(broker.equity(), sig.price, stop)
                        if qty <= 0:
                            continue

                        order = Order(symbol=symbol, side=sig.side.value, qty=qty,
                                      order_type=OrderType.MARKET,
                                      stop_loss=stop, take_profit=take,
                                      metadata={"strategy": strat.name, "market": market["name"],
                                                "reason": sig.reason})
                        filled = broker.submit(order)
                        log.info(f"Submitted {filled.side} {filled.qty:.6f} {symbol} @ {filled.fill_price}")
                        journal.record("order", {
                            "id": filled.id, "symbol": symbol, "side": filled.side,
                            "qty": filled.qty, "fill_price": filled.fill_price,
                            "status": filled.status.value, "strategy": strat.name,
                            "market": market["name"],
                        })
                        if filled.fill_price is not None:
                            risk.on_fill(broker.equity())
        except Exception as exc:  # don't crash the loop
            log.exception(f"Loop error: {exc}")
            journal.record("error", {"error": str(exc)})

        time.sleep(interval)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Multi-market trading bot")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.mode == "live":
        # Extra safety gate before real money
        cfg["mode"] = "live"
        raise SystemExit("Live mode not wired up yet. Use paper mode.")
    run(cfg, mode=args.mode)


if __name__ == "__main__":
    main()
