"""Logging setup using loguru (falls back to stdlib if unavailable)."""
from __future__ import annotations

import sys


def configure_logging(level: str = "INFO"):
    try:
        from loguru import logger

        logger.remove()
        logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:HH:mm:ss}</green> | "
                   "<level>{level:<8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | {message}",
        )
        return logger
    except ImportError:
        import logging
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        )
        return logging.getLogger("trading_bot")
