# The ten controls

Each control: the rule, when it applies, the smallest implementation, and how it is enforced.
"Enforced by" is part of the control. If you cannot name a check, the control is not met.

| # | Rule | Applies when | Smallest implementation | Enforced by |
|---|---|---|---|---|
| G1 | **Personal data goes only to vendors cleared for it.** | Any prompt carries names, emails or typed free text. | A per-vendor flag `allows_personal_data`, default false. The code that builds the vendor chain filters on it for any prompt that may contain personal data. Send only what the task needs (first name, role title, not the full record). Store no prompt text in the usage log. | A test that every vendor class sets the flag explicitly, and one that a personal-data chain never contains an uncleared vendor. |
| G2 | **Outside text is data, never instructions.** | Any prompt includes text the team did not write. | `wrap_untrusted(text, label)` fences the text between markers it cannot close itself, and a notice at the top of the prompt says marked text is data. Apply it in every prompt builder. | An architecture test: any file that builds a prompt must call the wrapper or be listed as exempt with a reason. A new prompt file fails until it does one or the other. |
| G3 | **Claims trace to evidence.** | Output states facts. | Require a verbatim quote and an evidence label for each claim, and verify the quote is in the evidence in code; drop what fails. Compute verdicts in code from verified claims, never take them from the model. For free text, check figures and past-work wording against the input and flag what is not there. | Eval metrics (citation survival, unsupported-claim rate); unit tests with a model that invents. |
| G4 | **A person decides; the model never approves its own work.** | Output is customer-facing, becomes a label, or triggers an action. | A review state (`needs_review`) with a person clearing it; an append-only log of each human decision with a snapshot of what they saw (never names or emails). A warning, enforced on the server, before hiding or discarding something with real history. | Tests that no code path clears the flag from model output; decision-log tests. |
| G5 | **Prompt and model changes come with an eval report.** | Prompts or models change over time. | A small eval harness: frozen inputs, code-graded checks, a runner a person runs on purpose, a report per task, prompt version and model. Injection and grounding cases first; accuracy cases once people have labelled real ones. | A check that every prompt version has a committed report covering every current case, with a shrink-only list for tasks still waiting for their first report. |
| G6 | **One place makes model calls.** | More than one call site. | A single helper that takes required `temperature`, `max_output_tokens` and schema, retries transient errors, makes one repair retry on an unreadable answer, and records usage. | An architecture test: no direct client construction outside the helper. |
| G7 | **Failures are bounded and visible.** | Always. | Backoff retries that distinguish a spent daily quota from a transient limit; vendor fallback; per-item error capture so one failure does not lose the batch; a failed call stores why it failed (shortened, keys removed). | Tests with fake clients for each failure type. |
| G8 | **Cost is measured and capped.** | Paid tier, or free tier you intend to leave. | Log provider, task, model, tokens (cached and thinking separately), latency, estimated cost, run and company on every call; a report by task and by failure reason. A per-run and daily ceiling that stops new model work and says so. | The report; a test that the ceiling blocks a call. |
| G9 | **Every AI-written row records which model and which prompt version wrote it.** | Output is stored. | Nullable `model_used` and `prompt_version` columns; the service that creates the row fills them. Old rows stay empty rather than carrying a guess. | An architecture test over the list of AI tables, with a shrink-only list of known gaps. |
| G10 | **Production switches are decided in advance.** | You may move to paid or production. | A table of switches (prompt caching, parallel calls, batch, routing, tracing, spending ceiling, vendor terms), each with a trigger and a design. | Reviewed at each release. |

## Phase order and why
Fence outside text (G2) before anything else: it is the largest risk and needs no data. Build the
single call helper (G6) early, because every later control (output caps, repair retries, metering,
fencing hooks) is cheaper when there is one place to put it. Evals (G5) come before routing or
model changes, because without them you cannot tell whether a cheaper model is good enough. A model
judge comes last, and only with labels.

## Production switches, in brief
| Switch | Turn on when | Notes |
|---|---|---|
| Prompt caching | Paid, and the usage report shows large repeated prompt starts | Keep prompts static-first. Read cached-token counts for implicit hits before paying for explicit caches. |
| Parallel calls | Higher limits, or jobs slower than target | One database session per task; a concurrency limit; a rate limiter honouring `Retry-After`; prefer more workers over bigger in-process fan-out. |
| Batch | A scheduled job that can wait up to a day exists, and billing is paid | Only for that job. Confirm availability and price then. |
| Routing | An eval report shows a cheaper model matches on a task | A per-task model setting changed only with a report. No routing classifier. |
| Tracing platform | Debugging needs more than the usage table | Self-hosted, or redact prompts. No hosted vendor sees personal data without G1 approval. |
| Spending ceiling | Paid key | Per run and daily; stops new work and says so; alert before the limit. |
