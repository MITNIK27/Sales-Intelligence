"""Canned in-memory generator for unit/integration tests — no network calls, no API key needed."""

from app.modules.ai_recommendation.models import Recommendation
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.draft.draft_generator import DraftGenerator, DraftResult
from app.modules.draft.evidence import DraftEvidence
from app.modules.draft.refine import RefineResult
from app.modules.products.models import Product


class MockDraftGenerator(DraftGenerator):
    def __init__(
        self, result: DraftResult | None = None, refined: RefineResult | None = None
    ) -> None:
        self.refine_calls: list[dict[str, object]] = []
        self._refined = refined
        self._result = result or DraftResult(
            subject="Canned subject for testing",
            body="Canned draft body for testing.",
            chosen_option=1,
        )

    @property
    def model_name(self) -> str:
        return "mock"

    async def generate(
        self,
        company: Company,
        contact: Contact,
        products: list[Product],
        recommendations: list[Recommendation | None],
        framing_style: str,
        draft_type: str,
        evidence: DraftEvidence | None = None,
        previous_emails: list[tuple[str | None, str]] | None = None,
    ) -> DraftResult:
        return self._result

    async def refine(
        self,
        company: Company,
        contact: Contact,
        product: Product,
        recommendation: Recommendation | None,
        framing_style: str,
        subject: str | None,
        body: str,
        instruction: str,
    ) -> RefineResult:
        self.refine_calls.append(
            {"subject": subject, "body": body, "instruction": instruction, "product": product.name}
        )
        return self._refined or RefineResult(subject=subject, body=f"{body} (rewritten)")
