"""What a company was searched for in Market Discovery, and the answer already on file for each
offering searched. The Brief shows it as soon as it opens, so nobody has to run a brief to see what
the search found. Fits are read from stored judgments (computed in code); nothing is asked of a
model here."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.jobs.models import STATUS_PENDING, STATUS_RUNNING, Job
from app.modules.opportunity.areas import normalize_area_key
from app.modules.opportunity.fit import latest_matches
from app.modules.opportunity.focus import (
    BAND_LABEL,
    best_known_match,
    company_runs,
    describe_run,
    load_focus,
    overall_matches,
    searched_for_run,
)
from app.modules.opportunity.jobs import JOB_TYPE_ANALYSE_OPPORTUNITY, JOB_TYPE_ASSESS_OPPORTUNITY
from app.modules.opportunity.models import GENERAL_AREA_KEY
from app.modules.opportunity.service import list_opportunities

MAX_RUNS = 5
MAX_QUOTES = 3

STATE_JUDGED = "judged"
STATE_WORKING = "working"
STATE_NOT_CHECKED = "not_checked"


async def _opportunities_being_worked_on(
    session: AsyncSession, organization_id: uuid.UUID
) -> set[str]:
    rows = (
        (
            await session.execute(
                select(Job).where(
                    Job.organization_id == organization_id,
                    Job.job_type.in_([JOB_TYPE_ANALYSE_OPPORTUNITY, JOB_TYPE_ASSESS_OPPORTUNITY]),
                    Job.status.in_([STATUS_PENDING, STATUS_RUNNING]),
                )
            )
        )
        .scalars()
        .all()
    )
    return {str((j.payload or {}).get("opportunity_id")) for j in rows}


def _criteria_names(raw: Any) -> list[str]:
    names = []
    for item in raw or []:
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


async def build_search_context(session: AsyncSession, company: Company) -> dict[str, Any]:
    org = company.organization_id
    runs = (await company_runs(session, org, company.id))[:MAX_RUNS]
    if not runs:
        return {"runs": []}

    overall = await overall_matches(session, org, company.id)
    opportunities = await list_opportunities(session, org, company.id)
    by_area = {o.area_key: o for o in opportunities}
    general = by_area.get(GENERAL_AREA_KEY)
    busy = await _opportunities_being_worked_on(session, org)

    out_runs: list[dict[str, Any]] = []
    for run in runs:
        offerings: list[dict[str, Any]] = []
        product_ids, found_by = await searched_for_run(session, run)
        for focus in await load_focus(session, org, product_ids):
            area = by_area.get(normalize_area_key(focus.area_label))
            own = await latest_matches(session, area.id) if area else {}
            match = best_known_match(focus.product_id, overall, own)
            working = (general is not None and str(general.id) in busy) or (
                area is not None and str(area.id) in busy
            )
            state = STATE_JUDGED if match else STATE_WORKING if working else STATE_NOT_CHECKED
            offerings.append(
                {
                    "product_id": str(focus.product_id),
                    "name": focus.name,
                    "kind": focus.kind,
                    "area_label": focus.area_label,
                    "area_id": str(area.id) if area else None,
                    "area_researched": bool(area and area.status == "active"),
                    "state": state,
                    "band": match.band if match else None,
                    "band_label": BAND_LABEL.get(match.band, match.band) if match else None,
                    "score": match.score if match else None,
                    "reasoning": match.reasoning if match else None,
                    "evidence": (match.evidence or [])[:MAX_QUOTES] if match else [],
                }
            )
        out_runs.append(
            {
                "run_id": str(run.id),
                "label": (run.raw_input or "").strip()[:200],
                "created_at": run.created_at.isoformat(),
                "searched": describe_run(run),
                "criteria": _criteria_names((run.context or {}).get("criteria")),
                "offerings": offerings,
                # "chosen" on the form, or "keywords": matched from the words that were searched.
                "offerings_found_by": found_by,
            }
        )
    return {"runs": out_runs}
