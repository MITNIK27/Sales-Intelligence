import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.contacts.schemas import ContactOut
from app.modules.draft.service import DraftNotFoundError
from app.modules.outreach.schemas import (
    LogOutreachActivityRequest,
    LogOutreachActivityResponse,
    OutreachActivityOut,
)
from app.modules.outreach.service import (
    ContactNotFoundError,
    list_outreach_activities,
    log_outreach_activity,
)

router = APIRouter(prefix="/contacts", tags=["outreach"])


@router.post(
    "/{contact_id}/outreach-activities",
    response_model=LogOutreachActivityResponse,
    status_code=201,
)
async def log_outreach_activity_endpoint(
    contact_id: uuid.UUID,
    body: LogOutreachActivityRequest,
    session: AsyncSession = Depends(get_db),
) -> LogOutreachActivityResponse:
    try:
        activity, contact = await log_outreach_activity(
            session,
            DEFAULT_ORGANIZATION_ID,
            contact_id,
            channel=body.channel,
            activity_type=body.activity_type,
            template_variant=body.template_variant,
            notes=body.notes,
            urgent=body.urgent,
            draft_id=body.draft_id,
        )
    except (ContactNotFoundError, DraftNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return LogOutreachActivityResponse(
        activity=OutreachActivityOut.model_validate(activity),
        contact=ContactOut.model_validate(contact),
    )


@router.get(
    "/{contact_id}/outreach-activities",
    response_model=list[OutreachActivityOut],
)
async def list_outreach_activities_endpoint(
    contact_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[OutreachActivityOut]:
    activities = await list_outreach_activities(session, DEFAULT_ORGANIZATION_ID, contact_id)
    return [OutreachActivityOut.model_validate(a) for a in activities]
