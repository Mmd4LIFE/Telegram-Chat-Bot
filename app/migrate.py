"""Programmatic Alembic upgrade, run on application startup."""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger("app.migrate")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_upgrade(revision: str = "head") -> None:
    """Apply migrations up to `revision` (default: head).

    Safe to call from a worker thread — env.py drives its own event loop.
    """
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    log.info("Running Alembic upgrade → %s", revision)
    command.upgrade(cfg, revision)
    log.info("Migrations applied.")
