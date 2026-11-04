# AI governance

_Created 2026-11-04. Decision record: [ADR 0014](decisions/0014-ai-governance.md)._

The rules this project follows wherever a language model is used: what must always be true, where
we are today, and which check keeps us honest. It is deliberately short. If a rule here is not
checked by something (a test, a review step, a number on the dashboard), it is a wish, so every
row names its check.

## How to use this file
- Before adding a prompt, a model call, a vendor or an AI-written table: read the rows that apply.
- Before changing a prompt or the model: see G5.
- The automated checks live in `backend/governance_checks/` and run with
  `pytest governance_checks` from `backend/`. They do not call any provider and need no keys.
- A check that is skipped says why and which phase turns it on. When a gap is fixed, remove it from
  that check's known-gaps list in the same change; the check fails if you forget.

## Controls
Status was verified in the code on 2026-11-04. "Gap" means we know it is not met yet.

| # | Rule | Today | Check |
|---|---|---|---|
| G1 | **Personal data only goes to vendors cleared for it.** Names and emails never go to a vendor that is not cleared; prompts are not stored beyond need. | Met. `allows_personal_data` on each vendor; Groq stays off until security confirms its terms (`groq_may_receive_personal_data=False`); drafts send first names only; `api_usage` stores no prompt text. | `tests/unit/test_llm_personal_data.py` (local) |
| G2 | **Web content is data, never instructions.** Scraped pages, search snippets, news and job posts are fenced and the model is told to ignore any instructions inside them. | Gap. No fencing or instruction found in the prompts. The code-side checks (schema, quote verification, verdicts computed in code) limit the damage but do not stop steering. | `governance_checks/test_untrusted_content_wrapped.py` (skipped until Phase 2) |
| G3 | **Every factual claim traces to supplied evidence.** | Met for Quick Look, opportunity research and offerings (quotes are verified against the source text). Partial for drafts: the prompt forbids inventing proof points, but nothing checks the finished email. | Eval metric "unsupported claim rate" (Phase 3) |
| G4 | **A person decides; the model never approves its own work.** Nothing customer-facing leaves without review, and every review decision is recorded. | Partly met. `needs_review` and approved proposals exist; the decision itself is not recorded when a flag is cleared. | Decision log (Phase 3) |
| G5 | **Prompt or model changes come with an eval report.** | Gap. No eval set yet. `prompt_version` only invalidates caches. | `governance_checks/test_prompt_version_has_eval_report.py` (skipped until Phase 3) |
| G6 | **One place makes model calls,** so temperature, output cap, thinking and retries are set once. | Met for Gemini. `generate_structured()` in `ai_recommendation/gemini_client.py` is the only place a Gemini client is built; every call passes an output cap (`MAX_OUTPUT_TOKENS`, 8192) and states its temperature. Temperature is still the provider default on all but the Groq-fallback path; setting it to 0 for judgments is a Phase 3 experiment, to be measured by evals. Thinking is not forced (see note below). | `governance_checks/test_single_gemini_entrypoint.py` (active) |
| G7 | **Failures are bounded and visible.** Retries with backoff, one repair retry on a bad answer, vendor fallback, per-item errors. | Met for Gemini. Retries and fallback as before; an unreadable answer now gets one repair try inside `generate_structured()`, and an answer cut off at the cap fails at once with a clear message. Groq has no repair try yet. | Unit tests with fake clients (`tests/unit/test_generate_structured.py`, local) |
| G8 | **Cost is measured and capped.** | Partly met. Calls, tokens, latency and estimated cost are logged per task, run and company, and cached and thinking tokens are now logged separately (`scripts/usage_report.py` shows them). Jobs name their calls from the job type, and every HTTP route now names them `api:<route>` (`usage/route_tag.py`), so little should be left under "unspecified". Price row unverified, no spending ceiling yet. | Dashboard; ceiling test (Phase 1) |
| G9 | **Every AI-written row says which model and which prompt version wrote it.** | Met for new rows. Every AI-written table has `model_used` and `prompt_version`; rows written before 2026-11-04 have them empty. Offering proposals made from a 404 check (removals) stay empty on purpose, since no model wrote them. | `governance_checks/test_ai_rows_record_model_and_prompt.py` (active) |
| G10 | **Production switches are decided in advance.** Caching, parallel calls, batch, routing and tracing each have a trigger and a design. | Written below. | Review at each release |

Note on thinking: `generate_structured()` only sends a thinking budget when a caller asks for one.
The default model name is a rolling alias, and some Gemini models cannot switch thinking off, so a
forced budget could fail every call. Thinking tokens are counted as output in the usage log.

## Production-readiness switches (G10)
Nothing here is needed on the free tier. Each item has a trigger, so it is switched on on purpose
and not by accident.

| Switch | Turn it on when | How |
|---|---|---|
| Prompt caching | Paid key, and the per-task token report shows large repeated prompt starts | Keep prompts static-first (instructions and examples before per-item data). Read cached-token counts for implicit hits before paying for explicit caches. Groq caches automatically. |
| Parallel model calls | Paid key with higher limits, or jobs slower than target | One database session per task (a session cannot be shared), a configurable concurrency limit, a per-provider rate limiter that honours `Retry-After`, and more job workers rather than bigger in-process fan-out. |
| Batch mode | A scheduled, non-urgent bulk job exists and billing is paid | Only for that job; it must tolerate up to a day of delay. Confirm availability and price then. |
| Model routing | An eval report shows a cheaper model matches (or a stronger one is clearly better) on a task | A per-task model setting changed only with an eval report. No routing classifier. |
| Tracing platform | Debugging needs more than the usage table gives | Self-hosted or OpenTelemetry with prompt redaction. No hosted vendor sees company or contact data without G1 approval. |

## Vendors
| Vendor | Used for | Personal data allowed | Terms status |
|---|---|---|---|
| Google Gemini | Most judgment and writing | Yes | Config note says use a paid key, whose terms do not train on input. Confirm before production. |
| Groq (gpt-oss) | Offerings import, triage, opportunity fallback | No, until InfoBeans security confirms | Pending |
| Serper, context.dev | Search and page reading (not language models) | n/a | n/a |

## Known documentation gap
Code and docs cite `docs/decisions/0012-context-dev-evaluation.md` and ADR 0013 (priority score),
but neither file exists. ADR 0014 was used for this decision so those numbers stay free.
