"""Generate a demo trade journal so the dashboard has data to display."""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


def write_demo(path: str = "/tmp/demo_journal.jsonl", seed: int = 7) -> None:
    rnd = random.Random(seed)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc) - timedelta(hours=6)
    equity_crypto = 10_000.0
    equity_stocks = 10_000.0
    lines: list[dict] = [{
        "ts": start.isoformat(), "event": "start",
        "payload": {"mode": "paper",
                    "markets": [["crypto", ["BTC/USDT", "ETH/USDT"], "PaperBroker"],
                                ["stocks", ["SPY", "AAPL"], "PaperBroker"]]},
    }]
    symbols = [("crypto", "BTC/USDT", 42_000.0, "ema_crossover"),
               ("crypto", "ETH/USDT", 2_500.0, "rsi_reversion"),
               ("stocks", "SPY", 500.0, "ema_crossover"),
               ("stocks", "AAPL", 190.0, "bollinger_squeeze")]
    regimes = ["trending_up", "trending_down", "ranging", "high_volatility"]
    prices = {sym: p for _, sym, p, _ in symbols}

    for step in range(72):  # 72 × 5-min slots ≈ 6h
        ts = start + timedelta(minutes=5 * step)
        for market, sym, _, strat in symbols:
            prices[sym] *= (1.0 + rnd.gauss(0, 0.004))
            regime = rnd.choices(regimes, weights=[4, 2, 3, 1])[0]
            lines.append({
                "ts": ts.isoformat(), "event": "regime_snapshot",
                "payload": {"market": market, "symbol": sym,
                            "regime": regime, "price": round(prices[sym], 4)},
            })
            if rnd.random() < 0.08:
                side = rnd.choice(["buy", "sell"])
                qty = round(rnd.uniform(0.01, 0.5) if market == "crypto"
                            else rnd.uniform(1, 10), 4)
                fill = round(prices[sym] * (1 + (0.0005 if side == "buy" else -0.0005)), 4)
                lines.append({
                    "ts": ts.isoformat(), "event": "order",
                    "payload": {"id": f"ord-{step}-{sym}", "market": market,
                                "symbol": sym, "side": side, "qty": qty,
                                "fill_price": fill, "status": "filled",
                                "strategy": strat, "broker": "PaperBroker"},
                })
                delta = (fill * qty * (1 if side == "sell" else -1)) + \
                        rnd.uniform(-20, 40)
                if market == "crypto":
                    equity_crypto += delta * 0.1
                else:
                    equity_stocks += delta * 0.05

        if step % 2 == 0:
            total = equity_crypto + equity_stocks
            lines.append({
                "ts": ts.isoformat(), "event": "equity_snapshot",
                "payload": {"equity": round(total, 2),
                            "brokers": [
                                {"market": "crypto", "broker": "PaperBroker",
                                 "equity": round(equity_crypto, 2)},
                                {"market": "stocks", "broker": "PaperBroker",
                                 "equity": round(equity_stocks, 2)},
                            ]},
            })

    with p.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    print(f"Wrote {len(lines)} events to {p}")


if __name__ == "__main__":
    write_demo()
