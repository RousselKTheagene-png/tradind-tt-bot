"""SQLite-backed trade journal.

Mirrors :class:`TradeJournal`'s ``record(event, payload)`` write API and adds
fast indexed query helpers for the dashboard. Falls back to writing the same
``{ts, event, payload}`` shape that the JSONL store uses, so consumers can
switch backends without changing event format.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    event   TEXT    NOT NULL,
    payload TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_event ON events(event);
CREATE INDEX IF NOT EXISTS idx_events_ts    ON events(ts);
"""


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


class SqliteJournal:
    """Append-only SQLite event store with the same shape as ``TradeJournal``."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path))
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ----- write API (mirrors TradeJournal) ------------------------------

    def record(self, event: str, payload: dict[str, Any]) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        body = json.dumps(payload, default=_serialize)
        with self._connect() as conn:
            conn.execute("INSERT INTO events (ts, event, payload) VALUES (?,?,?)",
                         (ts, event, body))

    # ----- read API ------------------------------------------------------

    def iter_events(self, *, event: Optional[str] = None,
                    limit: Optional[int] = None,
                    order: str = "asc") -> Iterable[dict[str, Any]]:
        order_sql = "DESC" if order.lower() == "desc" else "ASC"
        sql = "SELECT ts, event, payload FROM events"
        params: list[Any] = []
        if event is not None:
            sql += " WHERE event = ?"
            params.append(event)
        sql += f" ORDER BY id {order_sql}"
        if limit is not None and limit > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            for ts, evname, body in conn.execute(sql, params):
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    payload = {}
                yield {"ts": ts, "event": evname, "payload": payload}

    def count(self, event: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM events"
        params: list[Any] = []
        if event is not None:
            sql += " WHERE event = ?"
            params.append(event)
        with self._connect() as conn:
            (n,) = conn.execute(sql, params).fetchone()
            return int(n)

    def latest(self, event: Optional[str] = None) -> Optional[dict[str, Any]]:
        items = list(self.iter_events(event=event, limit=1, order="desc"))
        return items[0] if items else None


# ---------------------------------------------------------------------------
# Backend selection helpers shared by main.py and the dashboard.
# ---------------------------------------------------------------------------

def is_sqlite_path(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {".db", ".sqlite", ".sqlite3"}


def open_journal(path: str | Path):
    """Return a journal instance whose backend matches ``path``'s suffix."""
    if is_sqlite_path(path):
        return SqliteJournal(path)
    from .journal import TradeJournal
    return TradeJournal(path)


def iter_events_from(path: str | Path) -> Iterable[dict[str, Any]]:
    """Read ``{ts,event,payload}`` events from a JSONL or SQLite store."""
    p = Path(path)
    if is_sqlite_path(p):
        if not p.exists():
            return
        yield from SqliteJournal(p).iter_events()
        return
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
