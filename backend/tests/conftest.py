import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db import models as _models  # noqa: F401 - registers all models before create_all
from app.db.base import Base
from app.modules.auth.models import Organization


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(Organization(id=DEFAULT_ORGANIZATION_ID, name="Internal"))
        await session.commit()
        yield session

    await engine.dispose()


@pytest.fixture
def organization_id() -> uuid.UUID:
    return DEFAULT_ORGANIZATION_ID
