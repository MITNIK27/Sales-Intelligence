"""Role-Relevance Classification (Phase A3).

Titles for the same function aren't standardized across companies (e.g. "IT vendor" at one
company vs. "category procurement manager" at another), so contacts are classified against an
org-configurable catalog of role categories (`RoleCategory`) by inferred function rather than
title keyword-matching. The LLM matches each contact to the best-fitting category, or none; the
resulting priority is computed deterministically from the category's `is_primary_target` flag,
never inferred by the LLM — same "LLM judges narrowly, code decides the outcome" pattern as
Phase A2.2's qualification judgment. History is append-only (`RoleRelevanceResult`), same
reasoning as `QualificationResult`. See `docs/roadmap.md` and
`docs/decisions/0006-role-relevance-classification.md`.
"""
