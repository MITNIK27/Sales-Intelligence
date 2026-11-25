"""Types owned by the discovery agent module. Not reused ad hoc from other modules — this module
has its own vocabulary for a company at each stage of the pipeline (raw search hit -> extracted
name -> resolved company), so a caller can never confuse a half-processed result for a final one."""

from dataclasses import dataclass, field

# Several places in one search are sent as one `location` string separated by this, e.g.
# "Germany; France; Pune". A comma is not used because "Pune, India" is one place.
PLACE_SEPARATOR = ";"
MAX_PLACES = 5


def split_places(location: str | None) -> list[str]:
    """The places in a `location` string, tidied, without repeats (ignoring case), at most
    `MAX_PLACES`."""
    places: list[str] = []
    seen: set[str] = set()
    for part in (location or "").split(PLACE_SEPARATOR):
        place = " ".join(part.split())
        if place and place.lower() not in seen:
            seen.add(place.lower())
            places.append(place)
    return places[:MAX_PLACES]


@dataclass(frozen=True)
class MarketCriteria:
    """Target-market description the agent searches against. Deliberately plain (no per-field
    confidence wrapper like `ai_recommendation.gemini_client.MarketCriteria`) — by the time a
    Market Discovery run reaches the agent, the user has already confirmed these fields."""

    industry_keywords: list[str]
    # One place, or several separated by `PLACE_SEPARATOR`.
    location: str | None = None
    employee_size_range: str | None = None

    def places(self) -> list[str]:
        return split_places(self.location)


@dataclass(frozen=True)
class RawSearchResult:
    """One organic web search hit, before any interpretation."""

    title: str
    link: str
    snippet: str


@dataclass(frozen=True)
class ExtractedCompany:
    """A company name the extraction model read out of the search results, with two
    independent judgments:

    - `grounded_in_source`: the name is literally present in the text given to the model — guards
      against fabrication (an invented company).
    - `matches_criteria`: it plausibly fits the stated industry/location/size — guards against
      on-topic-but-irrelevant noise (a real company mentioned in the same article but the wrong
      fit). A different failure mode from fabrication, so kept as a separate flag rather than
      folded into one "valid" boolean.

    Only entries where both are true are eligible for domain resolution; everything else is kept
    in `DiscoveryResult.rejected` with its `reasoning`, not silently dropped.
    """

    name: str
    source_snippet: str
    grounded_in_source: bool
    matches_criteria: bool
    reasoning: str
    # Set by the deterministic listicle-name backstop in `agent.py` (`heuristics.py`), not by the
    # model — a structurally-suspicious-but-not-certain name is kept accepted but flagged, rather
    # than silently trusted or silently dropped.
    needs_review: bool = False
    needs_review_reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.grounded_in_source and self.matches_criteria


@dataclass(frozen=True)
class DiscoveredCompany:
    """A company that survived extraction and was resolved to a real domain — the agent's final
    output unit, ready to become a `Company` row."""

    name: str
    domain: str
    source_snippet: str
    needs_review: bool = False
    needs_review_reason: str | None = None
    # The extraction model's own explanation of why it accepted this company.
    reasoning: str = ""


@dataclass(frozen=True)
class DiscoveryResult:
    """The agent's full output for one `discover()` call: the final company list plus counts at
    each stage, so a run that comes back thin is debuggable (did search find nothing, did
    extraction reject everything, did resolution fail to find domains?) instead of a black box."""

    companies: list[DiscoveredCompany]
    raw_results_count: int
    extracted_count: int
    accepted_count: int
    resolved_count: int
    rejected: list[ExtractedCompany] = field(default_factory=list)
