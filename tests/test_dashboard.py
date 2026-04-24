"""Tests for the FastAPI dashboard."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.dashboard.app import create_app, _compute_positions


def _write_journal(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def _sample_events() -> list[dict]:
    return [
        {"ts": "2024-01-01T00:00:00Z", "event": "start",
         "payload": {"mode": "paper"}},
        {"ts": "2024-01-01T00:01:00Z", "event": "regime_snapshot",
         "payload": {"market": "crypto", "symbol": "BTC/USDT",
                     "regime": "trending_up", "price": 42000.0}},
        {"ts": "2024-01-01T00:02:00Z", "event": "order",
         "payload": {"id": "a1", "market": "crypto", "symbol": "BTC/USDT",
                     "side": "buy", "qty": 0.1, "fill_price": 42000.0,
                     "status": "filled", "strategy": "ema_crossover",
                     "broker": "PaperBroker"}},
        {"ts": "2024-01-01T00:03:00Z", "event": "order",
         "payload": {"id": "a2", "market": "crypto", "symbol": "BTC/USDT",
                     "side": "buy", "qty": 0.1, "fill_price": 43000.0,
                     "status": "filled", "strategy": "ema_crossover",
                     "broker": "PaperBroker"}},
        {"ts": "2024-01-01T00:04:00Z", "event": "order",
         "payload": {"id": "a3", "market": "crypto", "symbol": "ETH/USDT",
                     "side": "buy", "qty": 1.0, "fill_price": 2500.0,
                     "status": "filled", "strategy": "rsi_reversion",
                     "broker": "PaperBroker"}},
        {"ts": "2024-01-01T00:05:00Z", "event": "equity_snapshot",
         "payload": {"equity": 10500.0,
                     "brokers": [{"market": "crypto",
                                  "broker": "PaperBroker",
                                  "equity": 10500.0}]}},
        {"ts": "2024-01-01T00:06:00Z", "event": "regime_snapshot",
         "payload": {"market": "crypto", "symbol": "BTC/USDT",
                     "regime": "ranging", "price": 42500.0}},
        {"ts": "2024-01-01T00:07:00Z", "event": "equity_snapshot",
         "payload": {"equity": 10600.0,
                     "brokers": [{"market": "crypto",
                                  "broker": "PaperBroker",
                                  "equity": 10600.0}]}},
    ]


def test_health_reports_journal_path(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["exists"] is True


def test_health_works_when_journal_missing(tmp_path):
    jpath = tmp_path / "missing.jsonl"
    client = TestClient(create_app(jpath))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["exists"] is False


def test_equity_returns_snapshots_in_order(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    r = client.get("/equity")
    data = r.json()
    assert data["count"] == 2
    equities = [p["equity"] for p in data["points"]]
    assert equities == [10500.0, 10600.0]
    assert "brokers" in data["points"][0]


def test_equity_limit_tails_points(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    r = client.get("/equity?limit=1")
    assert r.json()["points"][0]["equity"] == 10600.0


def test_positions_aggregates_fills(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    data = client.get("/positions").json()
    by_key = {(p["market"], p["symbol"]): p for p in data["positions"]}
    btc = by_key[("crypto", "BTC/USDT")]
    assert btc["qty"] == 0.2
    assert abs(btc["avg_price"] - 42500.0) < 1e-6
    assert by_key[("crypto", "ETH/USDT")]["qty"] == 1.0


def test_positions_closes_out_with_offsetting_sells():
    events = [
        {"event": "order", "payload": {"market": "stocks", "symbol": "SPY",
                                       "side": "buy", "qty": 10,
                                       "fill_price": 500.0, "status": "filled"}},
        {"event": "order", "payload": {"market": "stocks", "symbol": "SPY",
                                       "side": "sell", "qty": 10,
                                       "fill_price": 510.0, "status": "filled"}},
    ]
    assert _compute_positions(events) == []


def test_positions_ignores_non_filled_orders():
    events = [
        {"event": "order", "payload": {"market": "stocks", "symbol": "SPY",
                                       "side": "buy", "qty": 5,
                                       "fill_price": 500.0,
                                       "status": "rejected"}},
    ]
    assert _compute_positions(events) == []


def test_journal_endpoint_filters_by_event(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    data = client.get("/journal?event=order").json()
    assert data["count"] == 3
    assert all(e["event"] == "order" for e in data["events"])


def test_journal_endpoint_limit(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    data = client.get("/journal?limit=2").json()
    assert len(data["events"]) == 2


def test_regime_returns_latest_per_symbol(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    data = client.get("/regime").json()
    assert data["count"] == 1
    assert data["regimes"][0]["regime"] == "ranging"


def test_regime_filter_by_symbol(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    r = client.get("/regime?symbol=ETH/USDT&market=crypto")
    assert r.status_code == 404


def test_index_page_served(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    _write_journal(jpath, _sample_events())
    client = TestClient(create_app(jpath))
    r = client.get("/")
    assert r.status_code == 200
    assert "Trading Bot" in r.text
    assert "text/html" in r.headers["content-type"]


def test_skips_malformed_lines(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    jpath.parent.mkdir(parents=True, exist_ok=True)
    with jpath.open("w", encoding="utf-8") as f:
        f.write("{not json}\n")
        f.write(json.dumps({"event": "equity_snapshot",
                            "ts": "t", "payload": {"equity": 100.0}}) + "\n")
    client = TestClient(create_app(jpath))
    data = client.get("/equity").json()
    assert data["count"] == 1
