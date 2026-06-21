"""Alembic environment — async engine, URL & metadata sourced from the app.

A `migrations` table is maintained (in addition to Alembic's own
`alembic_version`) logging every revision that is applied, with a timestamp and
direction. Logging is wired via the `on_version_apply` hook so it happens
automatically for every migration step.
"""
import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.database import Base
from app import models  # noqa: F401  (register all models on Base.metadata)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

# NOTE: we intentionally do NOT call logging.config.fileConfig here. Migrations
# run in-process during app startup, and fileConfig would reset the root logger
# (silencing the app/uvicorn loggers). The app configures logging itself.

target_metadata = Base.metadata


def _log_version_apply(ctx, step, heads, run_args):
    """Record each applied migration into the `migrations` log table.

    Runs automatically for every migration step, so future revisions are logged
    without any extra code. Fully guarded — a logging hiccup never breaks a
    migration (e.g. downgrading the very migration that creates this table).
    """
    try:
        direction = "upgrade" if step.is_upgrade else "downgrade"
        rev = getattr(step, "up_revision_id", None) or "?"
        revision_obj = getattr(step, "up_revision", None)
        doc = (getattr(revision_obj, "doc", "") or "").strip().splitlines()
        description = doc[0] if doc else None
        ctx.connection.execute(
            text(
                "INSERT INTO migrations (revision, description, direction) "
                "VALUES (:r, :d, :dir)"
            ),
            {"r": rev, "d": description, "dir": direction},
        )
    except Exception:  # noqa: BLE001
        pass


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        on_version_apply=_log_version_apply,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
