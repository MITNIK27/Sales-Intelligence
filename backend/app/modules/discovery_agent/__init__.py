"""Company Discovery Agent (Phase A1).

Turns a free-text market description into a list of real, relevant companies. Isolated on
purpose: this is the single most failure-sensitive step in the pipeline (a bad company list
poisons everything downstream), so it exposes one narrow interface — `CompanyDiscoveryAgent` in
`agent.py` — and contains any internal failure (search, LLM extraction, domain resolution) behind
one typed `DiscoveryAgentError` rather than leaking provider-specific exceptions to callers.

See `docs/decisions/0004-discovery-agent.md` for the architecture rationale.
"""
