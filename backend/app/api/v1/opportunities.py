import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.ai_recommendation.schemas import RecommendationOut
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.jobs.service import enqueue_job
from app.modules.opportunity.analysis import company_contacts
from app.modules.opportunity.fit import latest_matches
from app.modules.opportunity.jobs import (
    JOB_TYPE_ANALYSE_OPPORTUNITY,
    JOB_TYPE_ASSESS_OPPORTUNITY,
    JOB_TYPE_COMPANY_OFFERS,
    JOB_TYPE_RECOMMEND_OPPORTUNITY,
    JOB_TYPE_SUGGEST_AREAS,
)
from app.modules.opportunity.models import ORIGIN_MANUAL, STATUS_ACTIVE, CompanyOpportunity
from app.modules.opportunity.recommend import list_opportunity_recommendations
from app.modules.opportunity.relevance import clear_override, resolve_relevance, set_override
from app.modules.opportunity.schemas import (
    AnalyseRequest,
    AssessmentOut,
    AssessRequest,
    AssessStarted,
    ContactRelevanceOut,
    FitMatchOut,
    OpportunityCreateRequest,
    OpportunityOut,
    RecommendRequest,
    RelevanceOverrideRequest,
    SuggestRequest,
)
from app.modules.opportunity.service import (
    get_opportunity,
    get_or_create_opportunity,
    latest_assessment,
    list_opportunities,
)
from app.modules.products.models import Product

company_router = APIRouter(prefix="/companies", tags=["opportunities"])
router = APIRouter(prefix="/opportunities", tags=["opportunities"])


async def _with_assessment(
    session: AsyncSession, opportunity: CompanyOpportunity
) -> OpportunityOut:
    out = OpportunityOut.model_validate(opportunity)
    out.research = opportunity.research_log
    assessment = await latest_assessment(session, opportunity.id)
    out.assessment = AssessmentOut.model_validate(assessment) if assessment else None
    return out


@company_router.get("/{company_id}/opportunities", response_model=list[OpportunityOut])
async def list_company_opportunities_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[OpportunityOut]:
    opportunities = await list_opportunities(session, DEFAULT_ORGANIZATION_ID, company_id)
    return [await _with_assessment(session, o) for o in opportunities]


@company_router.post("/{company_id}/opportunities", response_model=OpportunityOut, status_code=201)
async def create_company_opportunity_endpoint(
    company_id: uuid.UUID,
    body: OpportunityCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> OpportunityOut:
    """Start looking into an area for this company. Asking for an area that already exists (however
    it is typed) returns it; a suggested one becomes active because somebody chose it."""
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != DEFAULT_ORGANIZATION_ID:
        raise HTTPException(status_code=404, detail="company not found")
    opportunity, _ = await get_or_create_opportunity(
        session, company, body.area_label, ORIGIN_MANUAL, STATUS_ACTIVE
    )
    if opportunity.status != STATUS_ACTIVE:
        opportunity.status = STATUS_ACTIVE
    await session.commit()
    return await _with_assessment(session, opportunity)


@company_router.post(
    "/{company_id}/opportunities/suggest", response_model=AssessStarted, status_code=202
)
async def suggest_areas_endpoint(
    company_id: uuid.UUID,
    body: SuggestRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> AssessStarted:
    """Look for other areas this company's evidence points to. Runs in the background; areas
    already suggested are kept, so asking again does not spend another model call, unless the
    request says `refresh`, which asks the model again and replaces the suggestions."""
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != DEFAULT_ORGANIZATION_ID:
        raise HTTPException(status_code=404, detail="company not found")
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_SUGGEST_AREAS,
        {"company_id": str(company.id), "refresh": bool(body and body.refresh)},
    )
    await session.commit()
    return AssessStarted(job_id=job.id)


@company_router.post(
    "/{company_id}/opportunities/offers", response_model=AssessStarted, status_code=202
)
async def research_offers_endpoint(
    company_id: uuid.UUID,
    body: AssessRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> AssessStarted:
    """Research what we could offer this company as a whole: its news, hiring and work in the areas
    we sell in, then every offering judged against it. Runs in the background."""
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != DEFAULT_ORGANIZATION_ID:
        raise HTTPException(status_code=404, detail="company not found")
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_COMPANY_OFFERS,
        {"company_id": str(company.id), "force": bool(body and body.force)},
    )
    await session.commit()
    return AssessStarted(job_id=job.id)


@router.get("/{opportunity_id}", response_model=OpportunityOut)
async def get_opportunity_endpoint(
    opportunity_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> OpportunityOut:
    opportunity = await get_opportunity(session, DEFAULT_ORGANIZATION_ID, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return await _with_assessment(session, opportunity)


@router.post("/{opportunity_id}/assess", response_model=AssessStarted, status_code=202)
async def assess_opportunity_endpoint(
    opportunity_id: uuid.UUID,
    body: AssessRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> AssessStarted:
    """Look into this area. Runs in the background; unchanged evidence is not judged again."""
    opportunity = await get_opportunity(session, DEFAULT_ORGANIZATION_ID, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_ASSESS_OPPORTUNITY,
        {"opportunity_id": str(opportunity.id), "force": bool(body and body.force)},
    )
    await session.commit()
    return AssessStarted(job_id=job.id)


@router.get("/{opportunity_id}/fit", response_model=list[FitMatchOut])
async def list_fit_endpoint(
    opportunity_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[FitMatchOut]:
    """The latest judgment for each offering that has been looked at, best fit first."""
    opportunity = await get_opportunity(session, DEFAULT_ORGANIZATION_ID, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    matches = await latest_matches(session, opportunity.id)
    products = {
        p.id: p
        for p in (
            await session.execute(select(Product).where(Product.id.in_(list(matches))))
        ).scalars()
    }
    out = [
        FitMatchOut(
            product_id=m.product_id,
            product_name=products[m.product_id].name,
            product_kind=products[m.product_id].kind,
            band=m.band,
            score=m.score,
            reasoning=m.reasoning,
            factors=m.factors,
            evidence=m.evidence,
            needs_review=m.needs_review,
            created_at=m.created_at,
        )
        for m in matches.values()
        if m.product_id in products
    ]
    return sorted(out, key=lambda m: -m.score)


@router.post("/{opportunity_id}/analyse", response_model=AssessStarted, status_code=202)
async def analyse_opportunity_endpoint(
    opportunity_id: uuid.UUID,
    body: AnalyseRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> AssessStarted:
    """Judge which offerings fit and who matters for them. Runs in the background; anything still
    valid from an earlier run is not judged again."""
    opportunity = await get_opportunity(session, DEFAULT_ORGANIZATION_ID, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    request = body or AnalyseRequest()
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_ANALYSE_OPPORTUNITY,
        {
            "opportunity_id": str(opportunity.id),
            "product_ids": [str(p) for p in request.product_ids],
            "with_contacts": request.with_contacts,
            "force": request.force,
        },
    )
    await session.commit()
    return AssessStarted(job_id=job.id)


@router.get("/{opportunity_id}/contacts", response_model=list[ContactRelevanceOut])
async def list_contact_relevance_endpoint(
    opportunity_id: uuid.UUID,
    product_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[ContactRelevanceOut]:
    """Every known person at the company with their part in this opportunity (for one offering
    when `product_id` is given). People not judged yet have no role."""
    opportunity = await get_opportunity(session, DEFAULT_ORGANIZATION_ID, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    resolved = await resolve_relevance(session, opportunity.id, product_id)
    contacts = await company_contacts(session, opportunity.company_id)
    out: list[ContactRelevanceOut] = []
    for contact in contacts:
        r = resolved.get(contact.id)
        out.append(
            ContactRelevanceOut(
                contact_id=contact.id,
                full_name=contact.full_name,
                role_title=contact.role_title,
                seniority=contact.seniority,
                contact_needs_review=contact.needs_review,
                role=r.role if r else None,
                function=r.function if r else None,
                reasoning=r.reasoning if r else None,
                confidence=r.confidence if r else None,
                needs_review=r.needs_review if r else False,
                source=r.source if r else None,
                note=r.note if r else None,
                model_role=r.model_role if r else None,
                model_reasoning=r.model_reasoning if r else None,
            )
        )
    return sorted(out, key=lambda c: (c.role is None, _ROLE_ORDER.get(c.role or "", 9)))


@router.put("/{opportunity_id}/contacts/{contact_id}/relevance", response_model=ContactRelevanceOut)
async def override_relevance_endpoint(
    opportunity_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: RelevanceOverrideRequest,
    session: AsyncSession = Depends(get_db),
) -> ContactRelevanceOut:
    """A person's own view of this contact's part. It wins over the model's, shown as theirs."""
    opportunity, contact = await _opportunity_and_contact(session, opportunity_id, contact_id)
    try:
        await set_override(session, opportunity, contact, body.product_id, body.role, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return await _one_contact(session, opportunity, contact, body.product_id)


@router.delete("/{opportunity_id}/contacts/{contact_id}/relevance", status_code=204)
async def clear_relevance_endpoint(
    opportunity_id: uuid.UUID,
    contact_id: uuid.UUID,
    product_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Withdraw a person's override so the model's judgment applies again."""
    opportunity, contact = await _opportunity_and_contact(session, opportunity_id, contact_id)
    await clear_override(session, opportunity, contact, product_id)
    await session.commit()


@router.post("/{opportunity_id}/recommendation", response_model=AssessStarted, status_code=202)
async def recommend_endpoint(
    opportunity_id: uuid.UUID,
    body: RecommendRequest,
    session: AsyncSession = Depends(get_db),
) -> AssessStarted:
    """Write the recommendation for this offering in this area. One per assessment version, so
    asking twice does not spend a second model call."""
    opportunity = await get_opportunity(session, DEFAULT_ORGANIZATION_ID, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_RECOMMEND_OPPORTUNITY,
        {
            "opportunity_id": str(opportunity.id),
            "product_id": str(body.product_id),
            "force": body.force,
        },
    )
    await session.commit()
    return AssessStarted(job_id=job.id)


@router.get("/{opportunity_id}/recommendations", response_model=list[RecommendationOut])
async def list_recommendations_endpoint(
    opportunity_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[RecommendationOut]:
    opportunity = await get_opportunity(session, DEFAULT_ORGANIZATION_ID, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    rows = await list_opportunity_recommendations(session, opportunity.id)
    return [RecommendationOut.model_validate(r) for r in rows]


_ROLE_ORDER = {"decision_maker": 0, "influencer": 1, "user": 2, "not_relevant": 3}


async def _opportunity_and_contact(
    session: AsyncSession, opportunity_id: uuid.UUID, contact_id: uuid.UUID
) -> tuple[CompanyOpportunity, Contact]:
    opportunity = await get_opportunity(session, DEFAULT_ORGANIZATION_ID, opportunity_id)
    contact = await session.get(Contact, contact_id)
    if opportunity is None or contact is None or contact.company_id != opportunity.company_id:
        raise HTTPException(status_code=404, detail="opportunity or contact not found")
    return opportunity, contact


async def _one_contact(
    session: AsyncSession,
    opportunity: CompanyOpportunity,
    contact: Contact,
    product_id: uuid.UUID | None,
) -> ContactRelevanceOut:
    r = (await resolve_relevance(session, opportunity.id, product_id)).get(contact.id)
    return ContactRelevanceOut(
        contact_id=contact.id,
        full_name=contact.full_name,
        role_title=contact.role_title,
        seniority=contact.seniority,
        contact_needs_review=contact.needs_review,
        role=r.role if r else None,
        function=r.function if r else None,
        reasoning=r.reasoning if r else None,
        confidence=r.confidence if r else None,
        needs_review=r.needs_review if r else False,
        source=r.source if r else None,
        note=r.note if r else None,
        model_role=r.model_role if r else None,
        model_reasoning=r.model_reasoning if r else None,
    )
