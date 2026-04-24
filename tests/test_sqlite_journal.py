"""Tests for monitoring.sqlite_journal."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from src.dashboard.app import create_app
from src.monitoring.journal import TradeJournal
from src.monitoring.sqlite_journal import (SqliteJournal, is_sqlite_path,
                                            iter_events_from, open_journal)


def _events() -> list[tuple[str, dict]]:
    return [
        ("start", {"mode": "paper"}),
        ("regime_snapshot", {"market": "crypto", "symbol": "BTC/USDT",
                             "regime": "trending_up", "price": 42000.0}),
        ("order", {"id": "a1", "market": "crypto", "symbol": "BTC/USDT",
                   "side": "buy", "qty": 0.1, "fill_price": 42000.0,
                   "status": "filled", "strategy": "ema_crossover",
                   "broker": "PaperBroker"}),
        ("equity_snapshot", {"equity": 10042.0,
                             "brokers": [{"market": "crypto", "equity": 10042.0}]}),
    ]


def test_is_sqlite_path_detects_known_suffixes(tmp_path):
    assert is_sqlite_path(tmp_path / "j.db")
    assert is_sqlite_path(tmp_path / "j.sqlite")
    assert is_sqlite_path(tmp_path / "j.sqlite3")
    assert not is_sqlite_path(tmp_path / "j.jsonl")
    assert not is_sqlite_path(tmp_path / "j")


def test_open_journal_picks_backend_by_suffix(tmp_path):
    j_db = open_journal(tmp_path / "x.db")
    j_jsonl = open_journal(tmp_path / "x.jsonl")
    assert isinstance(j_db, SqliteJournal)
    assert isinstance(j_jsonl, TradeJournal)


def test_record_persists_event_and_payload(tmp_path):
    j = SqliteJournal(tmp_path / "j.db")
    j.record("order", {"side": "buy", "qty": 1, "price": 100.0})
    rows = list(j.iter_events())
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "order"
    assert row["payload"] == {"side": "buy", "qty": 1, "price": 100.0}
    assert "T" in row["ts"]  # ISO-8601 timestamp


def test_iter_events_filter_and_order(tmp_path):
    j = SqliteJournal(tmp_path / "j.db")
    for name, p in _events():
        j.record(name, p)
    all_evs = list(j.iter_events())
    assert [e["event"] for e in all_evs] == [name for name, _ in _events()]

    orders = list(j.iter_events(event="order"))
    assert len(orders) == 1
    assert orders[0]["payload"]["id"] == "a1"

    desc = list(j.iter_events(order="desc", limit=2))
    assert [e["event"] for e in desc] == ["equity_snapshot", "order"]


def test_count_and_latest(tmp_path):
    j = SqliteJournal(tmp_path / "j.db")
    for name, p in _events():
        j.record(name, p)
    assert j.count() == 4
    assert j.count(event="order") == 1
    last = j.latest()
    assert last["event"] == "equity_snapshot"
    last_order = j.latest(event="order")
    assert last_order["payload"]["id"] == "a1"
    assert j.latest(event="missing") is None


def test_schema_indexes_present(tmp_path):
    p = tmp_path / "j.db"
    SqliteJournal(p).record("order", {"x": 1})
    with sqlite3.connect(str(p)) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_events_event" in names
    assert "idx_events_ts" in names


def test_iter_events_from_dispatches_on_suffix(tmp_path):
    db = tmp_path / "a.db"
    jsonl = tmp_path / "b.jsonl"
    SqliteJournal(db).record("order", {"id": "x"})
    jsonl.write_text(json.dumps({"ts": "2024-01-01T00:00:00Z",
                                  "event": "order",
                                  "payload": {"id": "y"}}) + "\n")
    db_events = list(iter_events_from(db))
    jl_events = list(iter_events_from(jsonl))
    assert db_events[0]["payload"] == {"id": "x"}
    assert jl_events[0]["payload"] == {"id": "y"}


def test_iter_events_from_missing_path_yields_nothing(tmp_path):
    assert list(iter_events_from(tmp_path / "nope.db")) == []
    assert list(iter_events_from(tmp_path / "nope.jsonl")) == []


def test_payload_with_non_jsonable_objects_serializes(tmp_path):
    from datetime import datetime, timezone
    j = SqliteJournal(tmp_path / "j.db")
    j.record("custom", {"when": datetime(2024, 1, 1, tzinfo=timezone.utc)})
    out = list(j.iter_events())
    assert out[0]["payload"]["when"].startswith("2024-01-01")


def test_dashboard_reads_sqlite_journal(tmp_path):
    db = tmp_path / "j.db"
    j = SqliteJournal(db)
    for name, p in _events():
        j.record(name, p)

    client = TestClient(create_app(db))
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["exists"] is True

    r = client.get("/journal")
    body = r.json()
    assert body["count"] == 4
    assert {e["event"] for e in body["events"]} == {
        "start", "regime_snapshot", "order", "equity_snapshot"}

    r = client.get("/positions")
    body = r.json()
    assert body["count"] == 1
    assert body["positions"][0]["symbol"] == "BTC/USDT"

    r = client.get("/equity")
    body = r.json()
    assert body["count"] == 1
    assert body["points"][0]["equity"] == 10042.0

    r = client.get("/regime?symbol=BTC/USDT")
    body = r.json()
    assert body["count"] == 1
    assert body["regimes"][0]["regime"] == "trending_up"


def test_record_is_append_only_across_instances(tmp_path):
    p = tmp_path / "j.db"
    SqliteJournal(p).record("order", {"id": 1})
    SqliteJournal(p).record("order", {"id": 2})
    rows = list(SqliteJournal(p).iter_events())
    assert [r["payload"]["id"] for r in rows] == [1, 2]
