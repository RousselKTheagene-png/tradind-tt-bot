"""Run the bot in paper mode against the dashboard's demo journal.

Loads config/config.yaml, overrides the journal path and loop interval so the
dashboard sees fresh activity quickly, and starts the live loop. Useful for
local previews; production should call ``python -m src.main`` directly with a
real config.
"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv

from src.execution.safety import ensure_live_safety
from src.main import load_config, run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--journal", default="/tmp/demo_journal.jsonl")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()

    load_dotenv()
    cfg = load_config(args.config)
    cfg["monitoring"]["journal_path"] = args.journal
    cfg["loop_interval_seconds"] = args.interval
    ensure_live_safety(cfg)
    run(cfg, mode="paper")


if __name__ == "__main__":
    main()
