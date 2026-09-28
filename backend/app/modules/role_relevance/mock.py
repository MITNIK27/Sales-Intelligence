"""Canned in-memory generator for unit/integration tests — no network calls, no API key needed."""

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.role_relevance.models import RoleCategory
from app.modules.role_relevance.role_relevance_generator import (
    ContactRoleVerdict,
    RoleRelevanceGenerator,
    RoleRelevanceJudgment,
)


class MockRoleRelevanceGenerator(RoleRelevanceGenerator):
    """Must return exactly one verdict per given contact (the real judgment core enforces this),
    so — unlike a single fixed canned result — this generates its response from whatever contacts
    it's actually called with. Default behavior: match every contact to the first given category
    (or `None` if there are none); pass an explicit `matches` dict (contact_id str -> category_id
    str | None) to control per-contact outcomes for a test."""

    def __init__(self, matches: dict[str, str | None] | None = None) -> None:
        self._matches = matches

    @property
    def model_name(self) -> str:
        return "mock"

    async def generate(
        self,
        company: Company,
        contacts: list[Contact],
        categories: list[RoleCategory],
    ) -> RoleRelevanceJudgment:
        default_category_id = str(categories[0].id) if categories else None
        return RoleRelevanceJudgment(
            contact_results=[
                ContactRoleVerdict(
                    contact_id=str(contact.id),
                    matched_category_id=(
                        self._matches.get(str(contact.id))
                        if self._matches is not None
                        else default_category_id
                    ),
                    reasoning="mock reasoning",
                )
                for contact in contacts
            ]
        )
