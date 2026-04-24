"""Outbound notifier (Telegram + Discord webhooks).

Sends short text alerts to one or more channels. All HTTP calls are wrapped in
a try/except so notification failures never break the trading loop.

Configuration (``notifier:`` section of config.yaml)::

    notifier:
      enabled: true
      events: [order, regime_flip, risk_block, error]   # which events to send
      telegram:
        enabled: true
        # token/chat_id read from env TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
      discord:
        enabled: true
        # webhook URL from env DISCORD_WEBHOOK_URL
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

DEFAULT_EVENTS = ("order", "regime_flip", "risk_block", "error")


@dataclass
class NotifierConfig:
    enabled: bool = False
    events: tuple[str, ...] = DEFAULT_EVENTS
    telegram_enabled: bool = False
    telegram_token: str = ""
    telegram_chat_id: str = ""
    discord_enabled: bool = False
    discord_webhook: str = ""

    @classmethod
    def from_cfg(cls, cfg: dict) -> "NotifierConfig":
        n = cfg.get("notifier") or {}
        tg = n.get("telegram") or {}
        dc = n.get("discord") or {}
        return cls(
            enabled=bool(n.get("enabled", False)),
            events=tuple(n.get("events") or DEFAULT_EVENTS),
            telegram_enabled=bool(tg.get("enabled", False)),
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            discord_enabled=bool(dc.get("enabled", False)),
            discord_webhook=os.getenv("DISCORD_WEBHOOK_URL", ""),
        )


@dataclass
class Notifier:
    config: NotifierConfig
    _senders: list[Callable[[str], None]] = field(default_factory=list)
    _last_regime: dict[tuple[str, str], str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.config.enabled:
            return
        if self.config.telegram_enabled and self.config.telegram_token \
                and self.config.telegram_chat_id:
            self._senders.append(self._send_telegram)
        if self.config.discord_enabled and self.config.discord_webhook:
            self._senders.append(self._send_discord)

    # ----- public API ----------------------------------------------------

    def send(self, event: str, text: str) -> None:
        if not self.config.enabled or event not in self.config.events:
            return
        for fn in self._senders:
            try:
                fn(f"[{event}] {text}")
            except Exception as exc:  # notifications must never crash the loop
                name = getattr(fn, "__name__", repr(fn))
                log.warning("notifier %s failed: %s", name, exc)

    def on_order(self, payload: dict[str, Any]) -> None:
        msg = (f"{payload.get('side', '?').upper()} {payload.get('qty')} "
               f"{payload.get('symbol')} @ {payload.get('fill_price')} "
               f"({payload.get('strategy')}, {payload.get('broker')})")
        self.send("order", msg)

    def on_regime_snapshot(self, market: str, symbol: str,
                           regime: str | None) -> None:
        if regime is None:
            return
        key = (market, symbol)
        prev = self._last_regime.get(key)
        self._last_regime[key] = regime
        if prev is not None and prev != regime:
            self.send("regime_flip",
                      f"{market}:{symbol} {prev} -> {regime}")

    def on_risk_block(self, symbol: str, reason: str) -> None:
        self.send("risk_block", f"{symbol} blocked: {reason}")

    def on_error(self, error: str) -> None:
        self.send("error", error)

    # ----- transports ----------------------------------------------------

    def _send_telegram(self, text: str) -> None:
        import requests
        url = f"https://api.telegram.org/bot{self.config.telegram_token}/sendMessage"
        r = requests.post(url, json={"chat_id": self.config.telegram_chat_id,
                                     "text": text}, timeout=5)
        r.raise_for_status()

    def _send_discord(self, text: str) -> None:
        import requests
        r = requests.post(self.config.discord_webhook,
                          json={"content": text}, timeout=5)
        r.raise_for_status()


def build_notifier(cfg: dict) -> Notifier:
    return Notifier(NotifierConfig.from_cfg(cfg))
