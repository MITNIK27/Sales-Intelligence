import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.db import models as _models  # noqa: F401 - registers all models for autogenerate
from app.db.base import Base
from app.db.session import connect_args

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    settings = get_settings()
    return settings.migration_database_url or settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # No statement limit (a migration may rewrite a table), a short lock wait (fail fast rather
    # than queue behind the running app), and named "<app>-migrations" in pg_stat_activity.
    settings = get_settings().model_copy(update={"database_url": get_url()})
    connectable = create_async_engine(get_url(), connect_args=connect_args(settings, "migrations"))
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
