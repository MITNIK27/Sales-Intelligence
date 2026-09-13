"""Canned in-memory parser/generator for unit/integration tests — no network calls, no API key
needed."""

from app.modules.ai_recommendation.gemini_client import MarketCriteria, MarketDescriptionParser
from app.modules.ai_recommendation.recommendation_generator import (
    RecommendationGenerator,
    RecommendationResult,
)
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.products.models import Product


class MockMarketDescriptionParser(MarketDescriptionParser):
    def __init__(self, result: MarketCriteria) -> None:
        self._result = result

    async def parse(self, raw_text: str) -> MarketCriteria:
        return self._result


class MockRecommendationGenerator(RecommendationGenerator):
    def __init__(self, result: RecommendationResult | None = None) -> None:
        self._result = result or RecommendationResult(
            pitch_summary="Canned pitch summary for testing.",
            why_this_company="Canned why-this-company reasoning for testing.",
            talking_points=["Talking point one", "Talking point two", "Talking point three"],
        )

    @property
    def model_name(self) -> str:
        return "mock"

    async def generate(
        self,
        company: Company,
        contacts: list[Contact],
        signals: list[EnrichmentRecord],
        product: Product,
    ) -> RecommendationResult:
        return self._result
