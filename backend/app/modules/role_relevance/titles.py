"""The job titles a people search looks for, read from the organisation's role categories rather
than built into the code. A category's description lists example titles after "e.g." (as the
role categories page asks), and those become the search terms, so editing a category changes who
is searched for."""

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enrichment.providers.base import SearchTitles
from app.modules.role_relevance.models import RoleCategory
from app.modules.role_relevance.service import list_active_categories

_EXAMPLES = re.compile(r"(?:e\.g\.|for example|such as)\s*:?\s*(.+)", re.IGNORECASE | re.DOTALL)
_SPLIT = re.compile(r"[,;]")
_PARENS = re.compile(r"\s*\([^)]*\)")
_MAX_WORDS = 6
_MAX_PER_GROUP = 12


def parse_example_titles(description: str | None) -> list[str]:
    """The titles listed after "e.g." in a category description, or none when it lists none.
    Titles are never invented from the category name."""
    match = _EXAMPLES.search(description or "")
    if not match:
        return []
    titles: list[str] = []
    for part in _SPLIT.split(match.group(1)):
        title = _PARENS.sub("", part).strip(" .\n\t")
        if 2 <= len(title) <= 60 and len(title.split()) <= _MAX_WORDS:
            titles.append(title)
    return titles


def titles_from_categories(categories: list[RoleCategory]) -> SearchTitles:
    def collect(wanted_primary: bool) -> tuple[str, ...]:
        seen: dict[str, str] = {}
        for category in categories:
            if category.is_primary_target != wanted_primary:
                continue
            for title in parse_example_titles(category.description):
                seen.setdefault(title.lower(), title)
        return tuple(seen.values())[:_MAX_PER_GROUP]

    return SearchTitles(primary=collect(True), other=collect(False))


async def load_search_titles(session: AsyncSession, organization_id: uuid.UUID) -> SearchTitles:
    return titles_from_categories(await list_active_categories(session, organization_id))
