import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.qualification.models import QualificationResult

_PROTOCOL_RE = re.compile(r"^https?://")
_WWW_RE = re.compile(r"^www\.")
# Search-result links are sometimes malformed at the source (observed live: Serper returning
# `https://www.knightfintech.com</b` — a literal stray closing HTML tag baked into the link
# field). Matches only the leading run of valid domain characters so garbage appended after the
# real domain (by a broken path split, e.g. `</b` has no `/` before the `<`) gets dropped instead
# of silently becoming part of the stored domain.
_VALID_DOMAIN_PREFIX_RE = re.compile(r"^[a-z0-9.-]+")


def normalize_domain(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().lower()
    value = _PROTOCOL_RE.sub("", value)
    value = _WWW_RE.sub("", value)
    value = value.rstrip("/")
    value = value.split("/")[0]  # drop any path component
    match = _VALID_DOMAIN_PREFIX_RE.match(value)
    value = match.group(0).strip(".-") if match else ""
    return value or None


def normalize_name(raw: str | None) -> str | None:
    if not raw:
        return None
    return " ".join(raw.strip().split()).lower() or None


def is_denylisted_domain(domain: str, denylist: list[str]) -> bool:
    """True if `domain` equals or is a subdomain of any entry in `denylist` (e.g.
    `careers.linkedin.com` matches `linkedin.com`)."""
    return any(domain == entry or domain.endswith(f".{entry}") for entry in denylist)


def _clean_company_name(name: str | None) -> str | None:
    """A name that's actually a URL (someone typed the site into the wrong field) gets cleaned
    the same way a domain would, rather than stored raw — e.g. "https://www.sennder.com/" becomes
    "sennder.com", not left as literal URL text. A genuine name (no protocol/www prefix) is only
    trimmed, never lowercased or otherwise mangled."""
    if name is None:
        return None
    stripped = name.strip()
    if not stripped:
        return None
    if _PROTOCOL_RE.match(stripped) or _WWW_RE.match(stripped):
        return normalize_domain(stripped) or stripped
    return stripped


async def get_or_create_company(
    session: AsyncSession,
    organization_id: uuid.UUID,
    name: str | None,
    domain: str | None,
    industry: str | None = None,
    employee_count_range: str | None = None,
    source_ingestion_run_id: uuid.UUID | None = None,
) -> tuple[Company, bool]:
    """Get-or-create with dedup by normalized domain, falling back to normalized name.
    Returns (company, created)."""
    name = _clean_company_name(name)
    normalized_domain = normalize_domain(domain)
    normalized_name = normalize_name(name)

    existing: Company | None = None
    if normalized_domain:
        stmt = select(Company).where(
            Company.organization_id == organization_id,
            func.lower(Company.domain) == normalized_domain,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
    elif normalized_name:
        # Only fall back to a name match when this row has no domain to key off of —
        # matching by name while a domain is present risks merging unrelated companies
        # that happen to share a display name.
        stmt = select(Company).where(
            Company.organization_id == organization_id,
            Company.domain.is_(None),
            func.lower(Company.name) == normalized_name,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing is not None:
        # Fill in blanks from this row rather than creating a duplicate.
        if not existing.domain and normalized_domain:
            existing.domain = normalized_domain
        if not existing.industry and industry:
            existing.industry = industry
        if not existing.employee_count_range and employee_count_range:
            existing.employee_count_range = employee_count_range
        await session.flush()
        return existing, False

    company = Company(
        organization_id=organization_id,
        name=name or domain or "Unknown",
        domain=normalized_domain,
        industry=industry,
        employee_count_range=employee_count_range,
        source_ingestion_run_id=source_ingestion_run_id,
    )
    session.add(company)
    await session.flush()
    return company, True


async def search_company_index(
    session: AsyncSession,
    organization_id: uuid.UUID,
    industry_keywords: list[str],
    limit: int,
) -> list[Company]:
    """The "compounding index" step for Market Discovery: check companies this org has already
    discovered/enriched before paying for a live search API call. Plain keyword matching against
    `industry`/`description` — a real, working first step, not the embeddings/semantic-matching
    version discussed as a future enhancement (no pgvector/pg_trgm infra exists yet)."""
    if not industry_keywords or limit <= 0:
        return []

    keyword_conditions = [
        or_(
            Company.industry.ilike(f"%{keyword}%"),
            Company.description.ilike(f"%{keyword}%"),
        )
        for keyword in industry_keywords
    ]
    stmt = (
        select(Company)
        .where(Company.organization_id == organization_id, or_(*keyword_conditions))
        .order_by(Company.last_enriched_at.desc().nulls_last())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_companies(
    session: AsyncSession, organization_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> tuple[list[tuple[Company, int, str | None]], int]:
    """Returns ([(company, contact_count, latest_qualification_verdict), ...], total_count)."""
    count_stmt = select(func.count()).select_from(Company).where(
        Company.organization_id == organization_id
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # QualificationResult is append-only — only the newest row per company matters for display,
    # not a count, so this ranks rows per company and keeps rank 1, rather than aggregating like
    # the Contact count below. A plain `DISTINCT ON` would be simpler but is Postgres-only and
    # silently wrong (picks an arbitrary row) elsewhere — ROW_NUMBER() is portable standard SQL.
    # Joining a company to at most one row here means it can't fan out the contact count.
    ranked_qual = select(
        QualificationResult.company_id,
        QualificationResult.overall_verdict,
        func.row_number()
        .over(
            partition_by=QualificationResult.company_id,
            order_by=QualificationResult.created_at.desc(),
        )
        .label("rn"),
    ).subquery()
    latest_qual = (
        select(ranked_qual.c.company_id, ranked_qual.c.overall_verdict)
        .where(ranked_qual.c.rn == 1)
    ).subquery()

    stmt = (
        select(Company, func.count(Contact.id), latest_qual.c.overall_verdict)
        .outerjoin(Contact, Contact.company_id == Company.id)
        .outerjoin(latest_qual, latest_qual.c.company_id == Company.id)
        .where(Company.organization_id == organization_id)
        .group_by(Company.id, latest_qual.c.overall_verdict)
        .order_by(Company.name)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1], row[2]) for row in rows], total


async def list_company_ids_by_source_run(
    session: AsyncSession, organization_id: uuid.UUID, source_ingestion_run_id: uuid.UUID
) -> list[uuid.UUID]:
    stmt = select(Company.id).where(
        Company.organization_id == organization_id,
        Company.source_ingestion_run_id == source_ingestion_run_id,
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_company_detail(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> Company | None:
    stmt = (
        select(Company)
        .where(Company.organization_id == organization_id, Company.id == company_id)
        .options(selectinload(Company.contacts).selectinload(Contact.channels))
    )
    return (await session.execute(stmt)).scalar_one_or_none()
