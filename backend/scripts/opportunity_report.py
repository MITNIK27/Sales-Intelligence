"""Read-only report of what the opportunity research produced for a company, for reviewing the
output together: each area with its verdict and findings, which offerings were judged and how,
and who matters for them. It changes nothing and calls no outside service.

Usage (from backend/, venv active):
    python scripts/opportunity_report.py                  # list companies that have opportunities
    python scripts/opportunity_report.py acme.com         # one company (name or domain)
"""

import argparse
import asyncio

from sqlalchemy import select

from app.db import models as _models  # noqa: F401 - registers all models with SQLAlchemy
from app.db.session import SessionLocal
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.opportunity.fit import latest_matches
from app.modules.opportunity.models import CompanyOpportunity
from app.modules.opportunity.relevance import resolve_relevance
from app.modules.opportunity.service import latest_assessment
from app.modules.products.models import Product


async def _list() -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Company.name, Company.domain)
                .join(CompanyOpportunity, CompanyOpportunity.company_id == Company.id)
                .distinct()
                .order_by(Company.name)
            )
        ).all()
    if not rows:
        print("No company has opportunities yet.")
    for name, domain in rows:
        print(f"{name}  ({domain or 'no domain'})")


async def _report(query: str) -> None:
    async with SessionLocal() as session:
        company = (
            (
                await session.execute(
                    select(Company).where(
                        (Company.domain == query.lower()) | (Company.name.ilike(f"%{query}%"))
                    )
                )
            )
            .scalars()
            .first()
        )
        if company is None:
            print(f"No company matches {query!r}.")
            return
        print(f"{company.name} ({company.domain})  industry: {company.industry or 'unknown'}\n")
        opportunities = (
            (
                await session.execute(
                    select(CompanyOpportunity).where(CompanyOpportunity.company_id == company.id)
                )
            )
            .scalars()
            .all()
        )
        products = {p.id: p for p in (await session.execute(select(Product))).scalars()}
        contacts = {
            c.id: c
            for c in (
                await session.execute(select(Contact).where(Contact.company_id == company.id))
            ).scalars()
        }
        for opportunity in opportunities:
            print(f"== {opportunity.area_label}  [{opportunity.status}, {opportunity.origin}]")
            if opportunity.suggestion_reason:
                print(f"   suggested because: {opportunity.suggestion_reason}")
            assessment = await latest_assessment(session, opportunity.id)
            if assessment:
                print(
                    f"   verdict: {assessment.verdict} (v{assessment.version}, "
                    f"{assessment.evidence_count} evidence, {assessment.dropped_count} dropped)"
                )
                print(f"   {assessment.summary}")
                for finding in assessment.findings:
                    ev = finding["evidence"]
                    print(f"   - [{finding['kind']}] {finding['statement']}")
                    print(f'       "{ev["quote"]}"  {ev.get("url") or ""}')
                for gap in assessment.not_found:
                    print(f"   not found: {gap}")
            for product_id, match in (await latest_matches(session, opportunity.id)).items():
                name = products[product_id].name if product_id in products else str(product_id)
                print(
                    f"   fit: {name}: {match.band} ({match.score})"
                    f"{' [check]' if match.needs_review else ''}"
                )
                print(f"       {match.reasoning}")
                resolved = await resolve_relevance(session, opportunity.id, product_id)
                for contact_id, r in resolved.items():
                    who = contacts.get(contact_id)
                    title = who.role_title if who else "?"
                    mark = " (set by a person)" if r.source == "human" else ""
                    print(f"       person: {title}: {r.role}{mark}")
            print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company", nargs="?", help="company name or domain")
    args = parser.parse_args()
    asyncio.run(_report(args.company) if args.company else _list())
