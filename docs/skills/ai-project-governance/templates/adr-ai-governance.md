# ADR NNNN: AI governance controls and how they are enforced

**Status:** accepted
**Date:** YYYY-MM-DD

## Context

TODO: where models are called, what text reaches them (especially text from outside the system and
anything personal), what they write, and what the first review found: the strengths and the real
gaps. Note where the team keeps its tests, because enforcement cannot depend on a folder that is not
committed.

## Decision

1. Adopt the controls in `docs/ai-governance.md` (G1 to G10) that apply, and say which do not.
2. Every control names its check. Checks that can run today are tracked in
   `TODO/governance_checks/` and run with `TODO command`; they need no keys and make no provider
   calls.
3. Checks that describe the current state are ratchets: a list of known gaps is allowed, a new gap
   fails, and a fixed gap that is still listed also fails. The lists only shrink.
4. Gaps are closed in phases: one shared model-call helper and usage logging, then fencing of
   outside text, then an in-house eval harness, then (only with labels) a model judge. Production
   switches are decided in advance, with triggers.
5. TODO: any platform deliberately not adopted now (a hosted tracing or eval service), and why.

## Consequences

- Easier: a reviewer has one list to check an AI change against, and drift shows up as a failing
  check.
- Harder: changing a prompt or model needs an eval report, which is extra work on purpose.
- Not covered: TODO (for example CI not yet running the checks).
- Revisit: when moving to a paid key or production traffic, and once the eval harness has real
  reports.
