"""Shows what the people search does for ONE company, step by step, so an empty result can be
explained. It makes real search calls (at most three Serper queries, about $0.003), so it is run
by a person on purpose and never by tests. Nothing is saved.

The titles searched for come from your role categories (their "e.g." examples), not from the code.

Usage (from backend/, venv active):
    python scripts/contact_search_probe.py "Infor" infor.com
    python scripts/contact_search_probe.py "Infor" infor.com --area "cloud migration"
"""

import argparse
import asyncio

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db import models as _models  # noqa: F401 - registers all models with SQLAlchemy
from app.db.session import SessionLocal
from app.modules.enrichment.providers.search_contacts import (
    SerperContactSearchProvider,
    build_contact_queries,
)
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.role_relevance.titles import load_search_titles


async def main(company: str, domain: str | None, area: str | None) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        titles = await load_search_titles(session, DEFAULT_ORGANIZATION_ID)
    print("Titles from your role categories")
    print(f"  first-reach: {', '.join(titles.primary) or '(none)'}")
    print(f"  others:      {', '.join(titles.other) or '(none)'}")
    queries = build_contact_queries(
        company, settings.contact_search_trusted_domains, area, None, titles
    )
    print(f"\n{len(queries)} search quer{'y' if len(queries) == 1 else 'ies'} will be made:")
    for query in queries:
        print(f"  {query}")
    if not queries:
        print("\nNothing to search for: add example titles (after 'e.g.') to a role category.")
        return

    search = SerperSearchProvider(settings)
    provider = SerperContactSearchProvider(settings, search)
    people = await provider.search_contacts(company, domain, focus=area, titles=titles)
    report = provider.last_report
    print(f"\n{report.line(company) if report else 'No report.'}")
    for person in people:
        print(f"  {person.full_name} | {person.role_title} | confidence {person.confidence}")
    if not people:
        print("  nobody kept")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company")
    parser.add_argument("domain", nargs="?")
    parser.add_argument("--area")
    args = parser.parse_args()
    asyncio.run(main(args.company, args.domain, args.area))
