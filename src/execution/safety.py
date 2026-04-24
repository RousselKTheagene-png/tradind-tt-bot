"""Live-trading safety gates.

Real-money execution must pass two independent checks:

1. ``live_safety.real_money_confirmed: true`` in config.yaml.
2. Environment variable ``TRADING_BOT_ALLOW_REAL_MONEY`` set to
   ``I_UNDERSTAND``.

If either is missing when any market has ``paper: false`` under ``mode: live``,
startup is aborted. Paper endpoints (Alpaca paper, OANDA practice) are allowed
in ``live`` mode without these gates.
"""
from __future__ import annotations

import os

ENV_VAR = "TRADING_BOT_ALLOW_REAL_MONEY"
ENV_EXPECTED = "I_UNDERSTAND"


def is_real_money_market(market_cfg: dict) -> bool:
    """Return True if this market's config requests a real-money endpoint."""
    if market_cfg.get("paper", True):
        return False
    # Forex also exposes environment=practice as a second dimension.
    if market_cfg.get("environment") == "practice":
        return False
    return True


def ensure_live_safety(cfg: dict) -> None:
    """Raise SystemExit unless real-money mode is explicitly confirmed.

    Only triggers when ``cfg['mode'] == 'live'`` and at least one enabled market
    is configured for a real-money endpoint.
    """
    if cfg.get("mode") != "live":
        return

    real_money_markets = [
        name for name, mcfg in cfg.get("markets", {}).items()
        if mcfg.get("enabled") and is_real_money_market(mcfg)
    ]
    if not real_money_markets:
        return

    confirmed = cfg.get("live_safety", {}).get("real_money_confirmed", False)
    env_ok = os.getenv(ENV_VAR, "") == ENV_EXPECTED
    if not (confirmed and env_ok):
        raise SystemExit(
            f"Real-money trading requested for {real_money_markets} but safety "
            f"gates not satisfied. Require live_safety.real_money_confirmed=true "
            f"in config AND env {ENV_VAR}={ENV_EXPECTED}."
        )
