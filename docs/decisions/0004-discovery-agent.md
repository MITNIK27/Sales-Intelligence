# ADR 0004: Company Discovery Agent Architecture

**Status:** accepted
**Date:** 2026-09-10

## Context

Market Discovery's candidate-finding was previously a single generic web search
(`SerperSearchProvider.find_candidates`) that treated every organic search-result link as a
candidate company, filtered only by a short static denylist of known aggregator domains. In
practice this returned mostly noise — directory pages, forum threads, "best of" roundup
articles — instead of an actual list of real target companies, which was confirmed live in a
working session and is the single most load-bearing step in the product: every downstream
step (qualification, contact targeting, outreach) is only as good as the company list it starts
from.

The fix requires an LLM-assisted extraction step (read search results, extract real company
names, then resolve each to a domain) rather than a bigger denylist, which can never generalize
to the long tail of noise sources. Given how failure-sensitive this step is — a bad result here
poisons everything downstream, with no real users of the system if it doesn't work — it needed
more architectural isolation than "a function in `market_discovery.py`."

## Decision

Built as its own module, `backend/app/modules/discovery_agent/`, with one narrow public
interface (`CompanyDiscoveryAgent.discover(criteria, limit) -> DiscoveryResult`) and internally
layered, independently testable stages:

- `search_gatherer.py` — pure I/O, issues multiple query variants, no interpretation.
- `extractor.py` — LLM extraction behind a model-agnostic `CompanyExtractionModel` interface.
  Two independent judgments per extracted name (`grounded_in_source`: is it actually in the
  text, guarding against fabrication; `matches_criteria`: does it fit the target market, guarding
  against on-topic-but-irrelevant noise) rather than one collapsed "valid" flag, so a bad run is
  debuggable rather than a black box.
- `resolver.py` — resolves accepted names to domains via the existing precise per-company
  `find_domain` lookup, with the denylist applied as a backstop.
- `agent.py` — composes the above, containing any internal failure (search, model, resolution)
  behind one typed `DiscoveryAgentError` so callers never depend on which search backend or
  model is behind a given run, and a failure here can't propagate a partially-broken state into
  `IngestionRun`/`Company`. No silent fallback to raw search links on failure.

This stays an **in-process module today**, not a second deployed service — consistent with the
existing minimal-infra philosophy (ADR 0001-0003). It is given the same "clean seam" shape the
architecture doc already uses for `enrichment/providers/`: one interface is all any caller
touches, so it can be moved behind an internal HTTP/RPC boundary later by changing only what
`get_default_discovery_agent()` constructs.

**Extraction model:** free-tier Gemini only (`GeminiCompanyExtractionModel`), consistent with
this being a free-tier application (no paid model or API key). The `CompanyExtractionModel`
interface stays generic so a different backend could be added later without touching
`prompts.py`/`agent.py`, but nothing paid is wired in. `discovery_agent_extraction_model`
(settings) lets this specific stage use a different, still-free-tier Gemini model (e.g. a "pro"
variant) than the rest of the app, independent of `gemini_model`.

**Prompt:** written as a standalone, provider-neutral asset (`prompts.py`) — plain instructions
and an output-field contract, not tied to Gemini's structured-output binding — so it stays
reusable if a second `CompanyExtractionModel` implementation is ever added, and is written to be
followable by a "basic" model, not relying on Gemini-specific tricks. It gives concrete negative
examples (a Reddit thread, a "10 best X" roundup) drawn from what was actually observed live,
rather than only an abstract instruction to avoid noise.

## Consequences

- Market Discovery candidates are now grounded, criteria-matched company names resolved to real
  domains, instead of raw (mostly irrelevant) search-result links.
- One additional LLM call per Market Discovery run (extraction), plus N per-company domain
  lookups (existing `find_domain`, now fanned out instead of called once per raw link) — bounded
  by `discovery_agent_resolution_concurrency`.
- No paid-model comparison was done (deferred, contingent on evidence free-tier Gemini quality is
  actually insufficient — see [`docs/roadmap.md`](../roadmap.md)) — quality
  is bounded by what free-tier Gemini can do at this task. If that proves insufficient later,
  the existing `CompanyExtractionModel` interface is the seam to add an alternative through.
- Phase A2 (qualification scoring) and A3 (role-relevance classification) build on this agent's
  output and should not start until it is verified end-to-end on real prompts.
