"""Canned in-memory generator for unit/integration tests — no network calls, no API key needed."""

from app.modules.ai_recommendation.models import Recommendation
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.draft.draft_generator import DraftGenerator, DraftResult
from app.modules.products.models import Product


class MockDraftGenerator(DraftGenerator):
    def __init__(self, result: DraftResult | None = None) -> None:
        self._result = result or DraftResult(
            subject="Canned subject for testing",
            body="Canned draft body for testing.",
        )

    @property
    def model_name(self) -> str:
        return "mock"

    async def generate(
        self,
        company: Company,
        contact: Contact,
        product: Product,
        recommendation: Recommendation | None,
        framing_style: str,
        draft_type: str,
    ) -> DraftResult:
        return self._result
