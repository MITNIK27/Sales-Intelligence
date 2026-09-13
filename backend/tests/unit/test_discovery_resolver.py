from app.modules.discovery_agent.resolver import CompanyResolver
from app.modules.discovery_agent.schemas import ExtractedCompany
from app.modules.enrichment.providers.base import DomainMatch


def _extracted(name: str, snippet: str = "snippet") -> ExtractedCompany:
    return ExtractedCompany(
        name=name,
        source_snippet=snippet,
        grounded_in_source=True,
        matches_criteria=True,
        reasoning="ok",
    )


class _FakeDomainProvider:
    def __init__(self, domains: dict[str, str | None]) -> None:
        self._domains = domains

    async def find_domain(self, company_name: str) -> DomainMatch | None:
        domain = self._domains.get(company_name)
        if domain is None:
            return None
        return DomainMatch(domain=domain, confidence="fuzzy")


async def test_resolve_maps_names_to_domains() -> None:
    resolver = CompanyResolver(
        _FakeDomainProvider({"Acme Parcel": "acmeparcel.com", "Globex Post": "globexpost.com"}),
        denylist=[],
    )
    resolved = await resolver.resolve([_extracted("Acme Parcel"), _extracted("Globex Post")])

    assert {c.domain for c in resolved} == {"acmeparcel.com", "globexpost.com"}


async def test_resolve_drops_companies_with_no_domain_found() -> None:
    resolver = CompanyResolver(_FakeDomainProvider({"Ghost Co": None}), denylist=[])
    resolved = await resolver.resolve([_extracted("Ghost Co")])

    assert resolved == []


async def test_resolve_applies_denylist_as_backstop() -> None:
    resolver = CompanyResolver(
        _FakeDomainProvider({"Fake Directory Listing": "crunchbase.com"}),
        denylist=["crunchbase.com"],
    )
    resolved = await resolver.resolve([_extracted("Fake Directory Listing")])

    assert resolved == []


async def test_resolve_dedupes_by_resolved_domain() -> None:
    resolver = CompanyResolver(
        _FakeDomainProvider({"Acme Parcel": "acme.com", "Acme Parcel Inc": "acme.com"}),
        denylist=[],
    )
    resolved = await resolver.resolve([_extracted("Acme Parcel"), _extracted("Acme Parcel Inc")])

    assert len(resolved) == 1
    assert resolved[0].domain == "acme.com"
