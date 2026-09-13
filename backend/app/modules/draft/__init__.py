"""Phase B — Outreach Draft Generation. Generates the actual first-touch/follow-up message a rep
sends, persona-tailored via Phase A3's role-relevance classification and grounded in Phase A/C's
existing Recommendation/Company data where available. Unlike the append-only judgment logs
elsewhere in this app (QualificationResult, RoleRelevanceResult, OutreachActivity), a Draft is a
work-in-progress document a human edits before sending — mutable, closer in spirit to
RoleCategory/Product than to those event logs."""
