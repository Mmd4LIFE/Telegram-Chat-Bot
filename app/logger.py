"""Centralized logging configuration.

A *logger* is the component that emits structured runtime messages — each tagged
with a severity (DEBUG/INFO/WARNING/ERROR), a timestamp and the module name —
so you can observe and debug the running service instead of using bare prints.

Call `setup_logging()` once at startup, then `get_logger(__name__)` anywhere.
"""
import logging

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Tame noisy third-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
