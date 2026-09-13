# ADR 0006: Role-Relevance Classification — Deterministic Priority, LLM Matches Only, Append-Only

**Status:** accepted
**Date:** 2026-09-11

## Context

Phase A3 turns a `Contact` into a role-relevance classification: which org-defined role category
(e.g. "Vendor / IT Procurement") the contact's function corresponds to, if any. This directly
answers a concrete requirement from the meeting this roadmap is built from: the same underlying
function has different titles at different companies (e.g. "IT vendor" at one company vs.
"category procurement manager" at another), so the system has to infer function from a title
rather than match a fixed title list, and needs to prioritize vendor/procurement/tech-evaluation-
adjacent roles over e.g. product managers for a first cold reach.

Three design questions carried over directly from A2.1/A2.2 (Qualification), reused here for the
same reasons:

## Decisions

1. **Role categories are an org-configurable catalog** (`RoleCategory`: `name`, `description`,
   `is_primary_target`, `is_active`), not hardcoded — same "explicit guardrails over inference"
   reasoning that produced `QualificationCriterion` in A2.1. `is_primary_target` is set explicitly
   by whoever defines the category, not inferred from its name/description at judgment time.

2. **The LLM matches; it does not prioritize.** For each contact, the LLM picks the single
   best-fitting `RoleCategory` id from the active list (or `null` if none genuinely fits),
   grounded in the contact's actual title/seniority text — never from general assumptions about
   what a title "usually" means. The resulting **priority** (`primary` / `secondary` /
   `not_relevant`) is computed **deterministically** in `role_relevance/service.py` from the
   matched category's `is_primary_target` flag, exactly mirroring ADR 0005's qualification-verdict
   gate: auditable Python logic, not a model inferring intent from wording. A `null` match is a
   valid, expected outcome (mirrors A2.2's "could_not_determine is not a failure"), not treated as
   an error.

3. **History is append-only** (`RoleRelevanceResult`, one row per contact per classification run),
   same spirit as `QualificationResult`. This was an explicit choice over a mutable
   current-classification field directly on `Contact`: a contact's title rarely changes once
   ingested, so the practical value isn't "track how the classification changed over time" so
   much as "don't silently overwrite a result an org might later want to build a manual-override
   feature on top of" — append-only was chosen specifically because it's easier to layer a
   mutable/override view on top of history later than to reconstruct history after the fact if a
   mutable-only model turns out to be insufficient.

4. **Snapshot, not live reference.** Each `RoleRelevanceResult` stores `matched_category_name` and
   `is_primary_target` as they were **at judgment time**, not as a live join to `RoleCategory` — a
   later rename, priority-flag change, or deletion of a category must never rewrite past
   classification history, same reasoning as `QualificationResult.criteria_results`.

## Consequences

- Adding a role category later doesn't retroactively change what already-classified contacts show
  — a re-classify is required to pick up new categories, same as re-checking qualification.
- Classification is batched per company (all of a company's contacts judged in one LLM call), for
  the same consistency/efficiency reasoning as A2.2 judging all criteria in one call.
- Because history is append-only rather than mutable+override, there is currently no way for a
  rep to directly correct a wrong classification — they can only re-run it (which won't help if
  the categories themselves are the problem) or add/adjust categories and re-run. A manual
  override affordance was explicitly deferred, not rejected — see `docs/roadmap.md`.
