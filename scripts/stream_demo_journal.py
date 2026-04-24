"""Append synthetic events to a journal so the dashboard reacts in real time.

Run alongside the dashboard:

    python -m scripts.stream_demo_journal --path /tmp/demo_journal.jsonl

It writes a regime_snapshot every tick, an equity_snapshot every few ticks,
and an occasional order / regime_block, using a small random walk so the
sparkline and chart stay alive without needing a real exchange feed.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path


SYMBOLS = [
    ("crypto", "BTC/USDT", 42_000.0, "ema_crossover"),
    ("crypto", "ETH/USDT",  2_500.0, "rsi_reversion"),
    ("stocks", "SPY",         500.0, "ema_crossover"),
    ("stocks", "AAPL",        190.0, "bollinger_squeeze"),
]
REGIMES = ["trending_up", "trending_down", "ranging", "high_volatility"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(path: Path, event: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def stream(path: str = "/tmp/demo_journal.jsonl",
           interval: float = 3.0,
           seed: int | None = None) -> None:
    rnd = random.Random(seed)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch(exist_ok=True)

    prices = {sym: base for _, sym, base, _ in SYMBOLS}
    equity = {"crypto": 10_000.0, "stocks": 10_000.0}
    tick = 0
    print(f"Streaming synthetic events into {p} every {interval}s. Ctrl-C to stop.")
    while True:
        market, sym, _, strat = rnd.choice(SYMBOLS)
        prices[sym] *= (1.0 + rnd.gauss(0, 0.0035))
        regime = rnd.choices(REGIMES, weights=[4, 2, 3, 1])[0]
        _append(p, {"ts": _now(), "event": "regime_snapshot",
                    "payload": {"market": market, "symbol": sym,
                                "regime": regime,
                                "price": round(prices[sym], 4)}})
        if rnd.random() < 0.18:
            side = rnd.choice(["buy", "sell"])
            qty = round(rnd.uniform(0.01, 0.5) if market == "crypto"
                        else rnd.uniform(1, 10), 4)
            fill = round(prices[sym] *
                         (1 + (0.0005 if side == "buy" else -0.0005)), 4)
            _append(p, {"ts": _now(), "event": "order",
                        "payload": {"id": f"sim-{tick}-{sym}",
                                    "market": market, "symbol": sym,
                                    "side": side, "qty": qty,
                                    "fill_price": fill, "status": "filled",
                                    "strategy": strat,
                                    "broker": "PaperBroker"}})
            equity[market] += rnd.uniform(-30, 60)
        elif rnd.random() < 0.05:
            _append(p, {"ts": _now(), "event": "regime_block",
                        "payload": {"market": market, "symbol": sym,
                                    "regime": regime, "strategy": strat}})
        if tick % 4 == 0:
            equity["crypto"] *= (1.0 + rnd.gauss(0, 0.0015))
            equity["stocks"] *= (1.0 + rnd.gauss(0, 0.0008))
            total = equity["crypto"] + equity["stocks"]
            _append(p, {"ts": _now(), "event": "equity_snapshot",
                        "payload": {"equity": round(total, 2),
                                    "brokers": [
                                        {"market": "crypto",
                                         "broker": "PaperBroker",
                                         "equity": round(equity["crypto"], 2)},
                                        {"market": "stocks",
                                         "broker": "PaperBroker",
                                         "equity": round(equity["stocks"], 2)},
                                    ]}})
        tick += 1
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="/tmp/demo_journal.jsonl")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    try:
        stream(args.path, args.interval, args.seed)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
