---
name: ai-project-governance
description: Use when starting a project that calls a language model, or when adding AI to an existing one (prompts, model calls, scraped or user text sent to a model, AI-written content, evals, cost control, prompt injection, "is this safe/production ready"). Walks through a short questionnaire, picks the governance controls that apply, and scaffolds the docs, enforcement checks, eval harness and audit columns, one phase at a time. Take only what fits the project.
---

# AI project governance

A set of controls for any project that uses a language model, learned on a real project (a sales
research tool on Gemini and Groq). It is built so that a rule is only counted as met when
something enforces it: a test, a review step or a number on a dashboard. A rule nobody checks is a
wish.

Use only what the project needs. A weekend script does not need all of this; a tool that writes to
customers from scraped web text needs most of it.

## How to use it

1. **Ask the questionnaire** in `references/questionnaire.md`. Ask the person; do not guess the
   answers. Record them.
2. **Pick the controls** that apply with the matrix in `references/controls.md`. Say which you are
   skipping and why. Write `docs/ai-governance.md` from `templates/ai-governance.md`, with an honest
   "today" column.
3. **Build in phases, one commit per phase**, each ending with a pause for the person:
   - **Phase 0, baseline:** governance doc, an ADR (`templates/adr-ai-governance.md`), a tracked
     folder for the enforcement checks, a PR checklist.
   - **Phase 1, one place for model calls:** a single helper that sets output cap, temperature,
     retries and metering; usage logging; `model_used` and `prompt_version` on every AI-written row.
   - **Phase 2, untrusted content and claims:** fence outside text in every prompt
     (`templates/llm/untrusted.py`); check finished text for invented figures and past work.
   - **Phase 3, evals and review log:** the eval harness (`templates/evals/`), a log of human
     decisions, and a check that a prompt change comes with a report.
   - **Phase 4, a model judge:** only once there are enough human labels to measure it against.
   - **Phase 5, production switches:** caching, parallel calls, batch, routing, tracing, a spending
     ceiling. Each has a trigger; turn it on when the trigger happens, not before.
4. **Verify what you built**: show the check failing on a deliberate violation, then restore it.
   A check you have never seen fail has not been shown to work.

## Rules that kept this honest

- **Ratchets.** Where the project has known gaps, list them in the check. A new gap fails, and a
  fixed gap that is still listed also fails, so the lists only shrink.
- **Enforcement lives in a tracked folder** (`governance_checks/`), not in a tests folder the team
  keeps local. A check that exists only on one machine is not a control.
- **Never use real provider keys in automatic tests.** Blank them in the test setup. Evals call real
  models only when a person runs them on purpose.
- **Prompt fencing is one layer, not a guarantee.** Say so in the doc. The limits that matter are in
  code: schema checks, quotes verified against the source, verdicts computed in code, a person
  reviewing anything customer-facing.
- **Personal data goes only to vendors cleared for it.** Make that a property of the vendor, checked
  by the code that builds the call chain.
- **The person runs migrations and commits.** Write the migration, preview its SQL
  (`alembic upgrade A:B --sql`), draft the commit message with an explicit file list, and stop.
  Name the phase in every commit title.
- **Say what you did not verify.** One run of a model that varies is not proof. A price that came
  from a summary is not confirmed. A screen you could not open has not been tested.

## What is in this skill

- `references/questionnaire.md`: what to ask at the start, and how the answers pick the controls.
- `references/controls.md`: the ten controls, when each applies, the smallest implementation, and
  how it is enforced.
- `references/lessons.md`: mistakes made and fixed on the first project. Read before building evals
  or a "not a fit"-style review action.
- `templates/`: documents and ready-to-copy code (`llm/untrusted.py`, enforcement checks, a minimal
  eval harness). Copy, then change the TODOs; none of it assumes a particular framework.
