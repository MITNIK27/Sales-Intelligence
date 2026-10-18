"""Read-only dashboard endpoints. GET only — nothing here may write (see dashboard/service.py)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.dashboard.schemas import Overview, RunList
from app.modules.dashboard.service import build_overview, list_run_stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=Overview)
async def get_overview(
    run_id: uuid.UUID | None = None,
    period: str = Query("all", pattern="^(7d|30d|all)$"),
    session: AsyncSession = Depends(get_db),
) -> Overview:
    """Everything the dashboard shows. Without `run_id` it covers all searches in `period`
    (companies de-duplicated); with `run_id` it covers that one search."""
    overview = await build_overview(session, DEFAULT_ORGANIZATION_ID, run_id, period)
    if overview is None:
        raise HTTPException(status_code=404, detail="search not found")
    return overview


@router.get("/runs", response_model=RunList)
async def get_runs(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    period: str = Query("all", pattern="^(7d|30d|all)$"),
    session: AsyncSession = Depends(get_db),
) -> RunList:
    return await list_run_stats(session, DEFAULT_ORGANIZATION_ID, limit, offset, period)
