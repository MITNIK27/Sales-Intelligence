"""The extraction prompt lives here as a standalone, provider-neutral asset: plain instructions
plus a description of the required output fields, not tied to any one SDK's structured-output
mechanism. Every `CompanyExtractionModel` implementation formats this same text and only swaps
how it binds the response to a schema, so if/when a second implementation is added, a comparison
run is a fair comparison of the model, not of two different prompts. Written to be followed by a
"basic" model, not relying on any model-specific tricks."""

from app.modules.discovery_agent.schemas import MarketCriteria, RawSearchResult

_PROMPT = """You are extracting a list of real, currently-operating companies from web search \
results, for a B2B sales research tool. Your output decides which companies a sales rep spends \
real time researching and reaching out to — precision matters more than recall. It is far better \
to return fewer, correct companies than to include noise.

Target market:
- Industry / business type: {industry_keywords}
- Location: {location}
- Employee size range: {employee_size_range}

Search results to read (numbered, each with a title, snippet, and source link):

{search_results}

For every company name you find mentioned anywhere in the text above, output one entry with:
- name: the company's name, exactly as it appears in the text.
- source_snippet: the exact sentence or phrase from the text that mentions this company, so a \
human can verify it against the source.
- grounded_in_source: true only if this exact company name is literally present in the text \
above. Never output a company you did not read in the text above — if you recognize the name \
from general knowledge but it is not actually written in the given text, this must be false.
- matches_criteria: true only if this company plausibly fits the target market described above \
(industry, location, and size if given). A real company that is mentioned in the text but is in \
the wrong industry, wrong location, or is itself a directory/review/news/social site rather than \
an operating company in the target market must have this set to false.
- reasoning: one sentence explaining both your grounded_in_source and matches_criteria judgment.

Do not include, under any circumstances:
- The directory, review, forum, listicle, or news site itself as if it were a company. Example: \
if one of the search results is a Reddit thread titled "Best courier companies in Europe?", the \
Reddit thread and Reddit itself are never a company — only extract the names of actual courier \
companies mentioned inside its text, each judged on its own.
- Example: if a search result is a blog post titled "Top 10 postal and parcel companies in \
2026", the blog and its publisher are never a company — only the 10 companies it actually names, \
each judged on its own.
- Job boards, recruiters, review platforms (G2, Capterra, Trustpilot), or industry-association \
bodies, unless one of them is itself the specific target company being described (rare).
- Any name you are not confident is a real, specific company, as opposed to a generic industry \
term, product name, or technology name.

If no company names can be confidently extracted from the text above, return an empty list — do \
not force results to fill a quota.
"""


def _format_search_results(results: list[RawSearchResult]) -> str:
    if not results:
        return "(no search results were found)"
    return "\n\n".join(
        f"[{i}] {r.title}\n{r.snippet}\n(source: {r.link})"
        for i, r in enumerate(results, start=1)
    )


def build_extraction_prompt(criteria: MarketCriteria, search_results: list[RawSearchResult]) -> str:
    return _PROMPT.format(
        industry_keywords=", ".join(criteria.industry_keywords) or "not specified",
        location=criteria.location or "not specified",
        employee_size_range=criteria.employee_size_range or "not specified",
        search_results=_format_search_results(search_results),
    )
