# ADR 0005: Qualification Scoring — Deterministic Overall Verdict, LLM Judges Only Per-Criterion

**Status:** accepted
**Date:** 2026-09-10

## Context

Phase A2 turns a `Company` into a qualified/not-qualified judgment against an org's own
qualification criteria (Phase A2.1: `QualificationCriterion`, a user-editable catalog — see
`docs/data-model.md`). The open question for A2.2 was how the *overall* qualified /
not_qualified / could_not_determine call gets made: should the LLM read all the criteria and
their wording and decide the overall verdict itself (as a first draft of this design sketched),
or should that decision be deterministic code?

## Decision

The LLM judges each criterion **individually** against the company's firmographics and signals,
returning `met` / `not_met` / `could_not_determine` per criterion with one sentence of reasoning
— nothing more. The **overall verdict is computed deterministically** in
`qualification/service.py`, keyed off `QualificationCriterion.is_disqualifying` (added in A2.1
specifically for this purpose):

- `not_qualified` if any `is_disqualifying` ("hard requirement") criterion is `not_met`.
- `could_not_determine` if none failed but any `is_disqualifying` criterion is
  `could_not_determine`.
- `qualified` otherwise.

Non-disqualifying ("soft") criteria are judged and shown per-criterion for the rep's context but
never flip the overall verdict on their own. An org with zero `is_disqualifying` criteria
configured gets `qualified` by default — nothing was set up to block it.

Each `QualificationResult.criteria_results` entry is a **snapshot** (`criterion_id`,
`criterion_name`, `is_disqualifying`, `verdict`, `reasoning`) taken at judgment time, not a live
reference to the `QualificationCriterion` row — a later edit to a criterion (name, description,
whether it's disqualifying) never rewrites past judgment history. `QualificationResult` is
append-only, same spirit as `Recommendation`: re-checking a company creates a new row so "was
this qualified before, and is it still now" is always answerable.

## Consequences

- The qualified/not-qualified gate is auditable, reproducible Python logic, not a model
  re-interpreting free-text wording differently across runs — directly addresses the product's
  explicit "explicit guardrails over inference" preference (the same reasoning that produced
  `is_disqualifying` as a field in A2.1 instead of leaving it implicit in criterion wording).
- The prompt (`qualification/prompts.py`) carries the actual quality burden: it has to get
  individual grounding right (evidence-based verdicts, no fabrication, no halo effect from a
  well-known company's reputation, silence treated as `could_not_determine` rather than
  `not_met`) since the downstream gate trusts its per-criterion output completely.
- Soft criteria currently have no effect on the overall verdict at all — they're informational
  only. If a future need arises for soft criteria to matter (e.g. a scoring/threshold model),
  that's a new decision made from evidence of that need, not backed into this phase.
- Zero-disqualifying-criteria orgs always get `qualified` — worth a UI nudge (not a code
  requirement) encouraging at least one hard requirement for the verdict to be meaningful.
