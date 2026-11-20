import ssl
from collections.abc import AsyncGenerator
from typing import Any, Literal

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

# Which process is talking to the database. It picks the timeouts and shows up in
# pg_stat_activity, so a slow query can be traced to the API, the worker or a migration.
DbRole = Literal["api", "worker", "migrations"]


def _ssl_arg(settings: Settings) -> ssl.SSLContext | str | None:
    if settings.db_ssl_mode == "disable":
        return None
    if settings.db_ssl_mode == "require":
        return "require"
    context = ssl.create_default_context(cafile=settings.db_ssl_root_cert)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def connect_args(settings: Settings, role: DbRole) -> dict[str, Any]:
    """asyncpg connection options for one process role. Empty for any other driver, so a test
    or tool pointing at a different database is not handed options it does not understand."""
    if not settings.database_url.startswith("postgresql+asyncpg"):
        return {}
    if role == "worker":
        statement_ms = settings.db_worker_statement_timeout_ms
        lock_ms = settings.db_worker_lock_timeout_ms
    elif role == "migrations":
        statement_ms = 0  # a migration may rewrite a whole table
        lock_ms = settings.db_migration_lock_timeout_ms
    else:
        statement_ms = settings.db_statement_timeout_ms
        lock_ms = settings.db_lock_timeout_ms
    args: dict[str, Any] = {
        "timeout": settings.db_connect_timeout_seconds,
        "server_settings": {
            "application_name": f"{settings.db_application_name}-{role}",
            "statement_timeout": str(statement_ms),
            "lock_timeout": str(lock_ms),
        },
    }
    ssl_arg = _ssl_arg(settings)
    if ssl_arg is not None:
        args["ssl"] = ssl_arg
    return args


def build_engine(role: DbRole = "api") -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.sql_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args=connect_args(settings, role),
    )


engine = build_engine("api")
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def use_role(role: DbRole) -> None:
    """Rebind the shared session factory to an engine for `role`. Called once at process start,
    before the first query (the job worker calls it with "worker"); every SessionLocal() after
    that uses the new engine."""
    global engine
    engine = build_engine(role)
    SessionLocal.configure(bind=engine)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
