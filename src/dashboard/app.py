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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from ..monitoring.sqlite_journal import iter_events_from
from .html import INDEX_HTML

_CHART_TTL = 30.0
_chart_cache: dict[tuple[str, str, str], tuple[float, Any]] = {}


def _fetch_ohlcv_df(exchange: str, symbol: str, timeframe: str, limit: int):
    """Fetch a DataFrame of OHLCV via ccxt and cache for ``_CHART_TTL`` seconds."""
    key = (exchange, symbol, timeframe)
    now = time.time()
    cached = _chart_cache.get(key)
    if cached and now - cached[0] < _CHART_TTL and len(cached[1]) >= limit:
        return cached[1].tail(limit)
    from ..data.crypto_provider import CryptoProvider
    prov = CryptoProvider(exchange=exchange)
    df = prov.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    _chart_cache[key] = (now, df)
    return df


def _candles_from_df(df) -> list[dict[str, Any]]:
    return [{"time": int(ts.timestamp()),
             "open": float(row.open), "high": float(row.high),
             "low":  float(row.low),  "close": float(row.close)}
            for ts, row in df.iterrows()]


def _series_points(times, series) -> list[dict[str, Any]]:
    import math
    out = []
    for t, v in zip(times, series):
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            continue
        out.append({"time": int(t), "value": f})
    return out


def _detect_patterns(df) -> list[dict[str, Any]]:
    """Detect common single/two-bar candlestick patterns.

    Returns one entry per matched candle: {time, name, label, bullish}.
    """
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    times = [int(ts.timestamp()) for ts in df.index]
    out: list[dict[str, Any]] = []
    for i in range(1, len(df)):
        body = abs(c[i] - o[i])
        rng = h[i] - l[i]
        if rng <= 0:
            continue
        upper = h[i] - max(c[i], o[i])
        lower = min(c[i], o[i]) - l[i]
        if lower >= 2 * body and upper / rng < 0.15 and lower / rng > 0.5:
            out.append({"time": times[i], "name": "hammer",
                        "label": "Hammer (bullish reversal)", "bullish": True})
            continue
        if upper >= 2 * body and lower / rng < 0.15 and upper / rng > 0.5:
            out.append({"time": times[i], "name": "shooting_star",
                        "label": "Shooting Star (bearish reversal)",
                        "bullish": False})
            continue
        if body / rng < 0.1:
            out.append({"time": times[i], "name": "doji",
                        "label": "Doji (indecision)", "bullish": None})
            continue
        if (c[i - 1] < o[i - 1] and c[i] > o[i]
                and o[i] <= c[i - 1] and c[i] >= o[i - 1]):
            out.append({"time": times[i], "name": "bull_engulfing",
                        "label": "Bullish Engulfing", "bullish": True})
            continue
        if (c[i - 1] > o[i - 1] and c[i] < o[i]
                and o[i] >= c[i - 1] and c[i] <= o[i - 1]):
            out.append({"time": times[i], "name": "bear_engulfing",
                        "label": "Bearish Engulfing", "bullish": False})
    return out


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

    @app.get("/signals")
    def signals(symbol: Optional[str] = None,
                limit: int = Query(200, ge=1, le=5000)) -> JSONResponse:
        """Return filled buy/sell orders, newest last, for chart overlays."""
        out: list[dict[str, Any]] = []
        for ev in _events():
            if ev.get("event") != "order":
                continue
            p = ev.get("payload", {})
            if p.get("status") != "filled":
                continue
            if symbol and p.get("symbol") != symbol:
                continue
            ts_iso = ev.get("ts") or ""
            try:
                t = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
                ts_unix = int(t.astimezone(timezone.utc).timestamp())
            except (ValueError, TypeError):
                continue
            out.append({
                "ts": ts_iso, "time": ts_unix,
                "symbol": p.get("symbol"), "market": p.get("market"),
                "side": p.get("side"), "qty": float(p.get("qty", 0.0)),
                "price": float(p.get("fill_price") or 0.0),
                "strategy": p.get("strategy"),
            })
        return JSONResponse({"count": len(out), "signals": _tail(out, limit)})

    @app.get("/chart")
    def chart(symbol: str = Query("BTC/USDT"),
              timeframe: str = Query("1h"),
              limit: int = Query(200, ge=20, le=1000),
              exchange: str = Query("kraken")) -> JSONResponse:
        try:
            df = _fetch_ohlcv_df(exchange, symbol, timeframe, limit)
            return JSONResponse({"symbol": symbol, "timeframe": timeframe,
                                 "exchange": exchange,
                                 "candles": _candles_from_df(df)})
        except Exception as exc:
            return JSONResponse(
                {"symbol": symbol, "timeframe": timeframe,
                 "exchange": exchange, "candles": [],
                 "error": str(exc)[:200]}, status_code=503)

    @app.get("/indicators")
    def indicators_route(symbol: str = Query("BTC/USDT"),
                         timeframe: str = Query("1h"),
                         limit: int = Query(200, ge=20, le=1000),
                         exchange: str = Query("kraken"),
                         which: str = Query("ema20,ema50,bb,rsi")) -> JSONResponse:
        try:
            from ..strategies.indicators import bollinger, ema, rsi
            df = _fetch_ohlcv_df(exchange, symbol, timeframe, limit)
            times = [int(ts.timestamp()) for ts in df.index]
            wanted = {x.strip() for x in which.split(",") if x.strip()}
            out: dict[str, Any] = {}
            if "ema20" in wanted:
                out["ema20"] = _series_points(times, ema(df["close"], 20))
            if "ema50" in wanted:
                out["ema50"] = _series_points(times, ema(df["close"], 50))
            if "bb" in wanted:
                u, m, l = bollinger(df["close"], 20, 2.0)
                out["bb_upper"] = _series_points(times, u)
                out["bb_mid"] = _series_points(times, m)
                out["bb_lower"] = _series_points(times, l)
            if "rsi" in wanted:
                out["rsi"] = _series_points(times, rsi(df["close"], 14))
            return JSONResponse({"symbol": symbol, "timeframe": timeframe,
                                 "indicators": out})
        except Exception as exc:
            return JSONResponse(
                {"symbol": symbol, "timeframe": timeframe,
                 "indicators": {}, "error": str(exc)[:200]},
                status_code=503)

    @app.get("/patterns")
    def patterns_route(symbol: str = Query("BTC/USDT"),
                       timeframe: str = Query("1h"),
                       limit: int = Query(200, ge=20, le=1000),
                       exchange: str = Query("kraken"),
                       max_results: int = Query(20, ge=1, le=200)) -> JSONResponse:
        try:
            df = _fetch_ohlcv_df(exchange, symbol, timeframe, limit)
            patterns = _detect_patterns(df)
            return JSONResponse({"symbol": symbol, "timeframe": timeframe,
                                 "count": len(patterns),
                                 "patterns": patterns[-max_results:]})
        except Exception as exc:
            return JSONResponse(
                {"symbol": symbol, "timeframe": timeframe,
                 "patterns": [], "error": str(exc)[:200]},
                status_code=503)

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
