# ADR 0014: AI governance controls and how they are enforced

**Status:** accepted
**Date:** 2026-11-04

## Context

The app calls language models in many places (Gemini and Groq) and feeds them text scraped from the
open web, sometimes including names and emails. A review on 2026-11-04 found the strengths (quotes
checked in code, verdicts computed in code, cost metering, a privacy switch for vendors) and some
real gaps: no way to measure model quality, seven separate copies of the Gemini call with settings
that differ, no defence against instructions hidden in scraped pages, and AI-written rows that do
not always record the model and prompt that wrote them.

Rules written in a document alone get forgotten. The project also keeps its own tests local (they
are in `.gitignore`), so enforcement cannot depend on them.

## Decision

1. Adopt the ten controls in [`docs/ai-governance.md`](../ai-governance.md) (G1-G10) as the standard
   for any AI feature in this project.
2. Every control names its check. Checks that can run today are tracked in
   `backend/governance_checks/` and run with `pytest governance_checks`; they need no keys and make
   no provider calls.
3. Checks that describe the current state are ratchets: a list of known gaps is allowed, a new gap
   fails, and a fixed gap that is still on the list also fails. The lists only shrink.
4. Gaps are closed in phases: one shared model-call helper and better usage logging first, then
   fencing of untrusted content, then an in-house eval harness, then an advisory model judge for
   Market Discovery. Production switches (caching, parallel calls, batch, routing, tracing) are
   decided in advance with triggers, not turned on ad hoc.
5. A hosted tracing or evaluation platform is not adopted now. A model judge is a technique that
   runs in our own harness and needs no extra vendor.
6. Once this has worked on this project, it is turned into a reusable skill for starting new AI
   projects.

## Consequences

- Easier: a reviewer has one list to check an AI change against, and drift shows up as a failing
  check instead of a surprise.
- Harder: changing a prompt or the model will need an eval report once Phase 3 lands, which is
  extra work on purpose.
- Not covered: CI does not run `governance_checks` yet, because the existing pipeline is already
  failing for unrelated reasons (type errors, and no tests on a clean checkout). Run them locally
  until the baseline is green, then add the job.
- Revisit: when moving to a paid key or production traffic (G10 switches), and when the eval
  harness exists (turn on the skipped checks).
