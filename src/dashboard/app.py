"""FastAPI dashboard reading from the trade journal.

The live loop appends events to ``monitoring.journal_path``; this app tails
that JSONL file and exposes the state over a tiny REST + HTML surface.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from ..monitoring.sqlite_journal import iter_events_from
from .html import INDEX_HTML

_CHART_TTL = 30.0
_chart_cache: dict[tuple[str, str, str], tuple[float, list[dict[str, Any]]]] = {}


def _fetch_candles(exchange: str, symbol: str, timeframe: str,
                   limit: int) -> list[dict[str, Any]]:
    """Fetch OHLCV via ccxt and cache for ``_CHART_TTL`` seconds."""
    key = (exchange, symbol, timeframe)
    now = time.time()
    cached = _chart_cache.get(key)
    if cached and now - cached[0] < _CHART_TTL:
        return cached[1][-limit:]
    from ..data.crypto_provider import CryptoProvider
    prov = CryptoProvider(exchange=exchange)
    df = prov.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    candles = [{"time": int(ts.timestamp()),
                "open": float(row.open), "high": float(row.high),
                "low":  float(row.low),  "close": float(row.close)}
               for ts, row in df.iterrows()]
    _chart_cache[key] = (now, candles)
    return candles


def _iter_events(path: Path) -> Iterable[dict[str, Any]]:
    yield from iter_events_from(path)


def _tail(events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return events
    return events[-limit:]


def _compute_positions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconstruct net positions per (market, symbol) from filled orders."""
    agg: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"qty": 0.0, "cost": 0.0}
    )
    for ev in events:
        if ev.get("event") != "order":
            continue
        p = ev.get("payload", {})
        if p.get("status") != "filled":
            continue
        key = (p.get("market", ""), p.get("symbol", ""))
        qty = float(p.get("qty", 0.0))
        price = float(p.get("fill_price") or 0.0)
        side = p.get("side")
        signed = qty if side == "buy" else -qty
        pos = agg[key]
        if (pos["qty"] >= 0 and signed > 0) or (pos["qty"] <= 0 and signed < 0):
            pos["cost"] += signed * price
        else:
            # closing or flipping: keep cost basis on residual only
            remaining = pos["qty"] + signed
            if pos["qty"] == 0:
                avg = 0.0
            else:
                avg = pos["cost"] / pos["qty"]
            pos["cost"] = remaining * avg
        pos["qty"] += signed
    out = []
    for (market, symbol), pos in agg.items():
        if abs(pos["qty"]) < 1e-12:
            continue
        avg_price = pos["cost"] / pos["qty"] if pos["qty"] else 0.0
        out.append({"market": market, "symbol": symbol,
                    "qty": pos["qty"], "avg_price": avg_price})
    return out


def create_app(journal_path: str | Path) -> FastAPI:
    app = FastAPI(title="Trading Bot Dashboard", version="0.1.0")
    jpath = Path(journal_path)

    def _events() -> list[dict[str, Any]]:
        return list(_iter_events(jpath))

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "journal": str(jpath), "exists": jpath.exists()}

    @app.get("/equity")
    def equity(limit: int = Query(500, ge=0, le=10_000)) -> JSONResponse:
        points = [
            {"ts": ev.get("ts"), **ev.get("payload", {})}
            for ev in _events() if ev.get("event") == "equity_snapshot"
        ]
        return JSONResponse({"count": len(points), "points": _tail(points, limit)})

    @app.get("/positions")
    def positions() -> JSONResponse:
        pos = _compute_positions(_events())
        return JSONResponse({"count": len(pos), "positions": pos})

    @app.get("/journal")
    def journal(limit: int = Query(100, ge=1, le=10_000),
                event: Optional[str] = None) -> JSONResponse:
        evs = _events()
        if event:
            evs = [e for e in evs if e.get("event") == event]
        return JSONResponse({"count": len(evs), "events": _tail(evs, limit)})

    @app.get("/regime")
    def regime(symbol: Optional[str] = None,
               market: Optional[str] = None) -> JSONResponse:
        """Latest regime_snapshot per (market, symbol), optionally filtered."""
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for ev in _events():
            if ev.get("event") != "regime_snapshot":
                continue
            p = ev.get("payload", {})
            key = (p.get("market", ""), p.get("symbol", ""))
            latest[key] = {"ts": ev.get("ts"), **p}
        items = list(latest.values())
        if symbol:
            items = [i for i in items if i.get("symbol") == symbol]
        if market:
            items = [i for i in items if i.get("market") == market]
        if symbol and market and not items:
            raise HTTPException(status_code=404, detail="no regime data")
        return JSONResponse({"count": len(items), "regimes": items})

    @app.get("/chart")
    def chart(symbol: str = Query("BTC/USDT"),
              timeframe: str = Query("1h"),
              limit: int = Query(200, ge=20, le=1000),
              exchange: str = Query("kraken")) -> JSONResponse:
        try:
            candles = _fetch_candles(exchange, symbol, timeframe, limit)
            return JSONResponse({"symbol": symbol, "timeframe": timeframe,
                                 "exchange": exchange, "candles": candles})
        except Exception as exc:
            return JSONResponse(
                {"symbol": symbol, "timeframe": timeframe,
                 "exchange": exchange, "candles": [],
                 "error": str(exc)[:200]}, status_code=503)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    return app


def main() -> None:
    import uvicorn
    parser = argparse.ArgumentParser(description="Trading bot dashboard")
    parser.add_argument("--journal", default=os.getenv(
        "TRADING_BOT_JOURNAL", "logs/journal.jsonl"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.journal), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
