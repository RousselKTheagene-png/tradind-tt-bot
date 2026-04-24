"""Tests for monitoring.notifier."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.monitoring.notifier import (DEFAULT_EVENTS, Notifier, NotifierConfig,
                                     build_notifier)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)


def test_disabled_notifier_sends_nothing():
    n = Notifier(NotifierConfig(enabled=False))
    n._senders.append(MagicMock())  # would-be sender
    n.send("order", "hi")
    assert n._senders[0].call_count == 0


def test_event_filter_blocks_disallowed_events():
    sender = MagicMock()
    n = Notifier(NotifierConfig(enabled=True, events=("order",)))
    n._senders = [sender]
    n.send("regime_flip", "BTC bull -> bear")
    sender.assert_not_called()
    n.send("order", "buy 1 BTC")
    sender.assert_called_once()


def test_send_dispatches_to_all_senders_with_prefix():
    a, b = MagicMock(), MagicMock()
    n = Notifier(NotifierConfig(enabled=True))
    n._senders = [a, b]
    n.send("order", "buy 1 BTC")
    a.assert_called_once_with("[order] buy 1 BTC")
    b.assert_called_once_with("[order] buy 1 BTC")


def test_sender_failure_does_not_propagate():
    bad = MagicMock(side_effect=RuntimeError("network down"))
    good = MagicMock()
    n = Notifier(NotifierConfig(enabled=True))
    n._senders = [bad, good]
    n.send("order", "x")  # must not raise
    good.assert_called_once()


def test_on_order_formats_payload():
    sender = MagicMock()
    n = Notifier(NotifierConfig(enabled=True))
    n._senders = [sender]
    n.on_order({"side": "buy", "qty": 0.5, "symbol": "BTC/USDT",
                "fill_price": 30000.0, "strategy": "ema_crossover",
                "broker": "PaperBroker"})
    msg = sender.call_args[0][0]
    assert "[order]" in msg and "BUY" in msg and "BTC/USDT" in msg


def test_on_regime_snapshot_only_fires_on_flip():
    sender = MagicMock()
    n = Notifier(NotifierConfig(enabled=True))
    n._senders = [sender]
    n.on_regime_snapshot("crypto", "BTC/USDT", "trend_up")
    n.on_regime_snapshot("crypto", "BTC/USDT", "trend_up")
    sender.assert_not_called()
    n.on_regime_snapshot("crypto", "BTC/USDT", "range")
    sender.assert_called_once()
    assert "trend_up -> range" in sender.call_args[0][0]


def test_on_regime_snapshot_ignores_none():
    sender = MagicMock()
    n = Notifier(NotifierConfig(enabled=True))
    n._senders = [sender]
    n.on_regime_snapshot("crypto", "BTC/USDT", None)
    sender.assert_not_called()


def test_on_risk_block_and_on_error_route_correctly():
    sender = MagicMock()
    n = Notifier(NotifierConfig(enabled=True))
    n._senders = [sender]
    n.on_risk_block("BTC/USDT", "max_daily_loss")
    n.on_error("provider timeout")
    msgs = [c[0][0] for c in sender.call_args_list]
    assert any("[risk_block]" in m and "max_daily_loss" in m for m in msgs)
    assert any("[error]" in m and "provider timeout" in m for m in msgs)


def test_telegram_transport_posts_to_bot_api():
    cfg = NotifierConfig(enabled=True, telegram_enabled=True,
                         telegram_token="TKN", telegram_chat_id="42")
    n = Notifier(cfg)
    with patch("requests.post") as post:
        post.return_value = MagicMock(raise_for_status=lambda: None)
        n._send_telegram("hello")
        url = post.call_args[0][0]
        body = post.call_args.kwargs["json"]
    assert "api.telegram.org/botTKN/sendMessage" in url
    assert body == {"chat_id": "42", "text": "hello"}


def test_discord_transport_posts_to_webhook():
    cfg = NotifierConfig(enabled=True, discord_enabled=True,
                         discord_webhook="https://discord/webhook/xyz")
    n = Notifier(cfg)
    with patch("requests.post") as post:
        post.return_value = MagicMock(raise_for_status=lambda: None)
        n._send_discord("hello")
    assert post.call_args[0][0] == "https://discord/webhook/xyz"
    assert post.call_args.kwargs["json"] == {"content": "hello"}


def test_build_notifier_reads_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://d/w")
    cfg = {"notifier": {
        "enabled": True,
        "telegram": {"enabled": True},
        "discord": {"enabled": True},
    }}
    n = build_notifier(cfg)
    assert n.config.telegram_token == "ABC"
    assert n.config.telegram_chat_id == "1"
    assert n.config.discord_webhook == "https://d/w"
    # both transports registered
    assert len(n._senders) == 2


def test_build_notifier_skips_transport_without_credentials():
    cfg = {"notifier": {"enabled": True,
                        "telegram": {"enabled": True},
                        "discord": {"enabled": True}}}
    n = build_notifier(cfg)
    # No env -> no senders attached
    assert n._senders == []


def test_default_events_constant_unchanged():
    assert DEFAULT_EVENTS == ("order", "regime_flip", "risk_block", "error")
