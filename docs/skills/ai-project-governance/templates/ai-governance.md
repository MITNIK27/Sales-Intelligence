# AI governance

_Created YYYY-MM-DD. Decision record: ADR NNNN._

The rules this project follows wherever a language model is used: what must always be true, where
we are today, and which check keeps us honest. If a rule here is not checked by something (a test, a
review step, a number on a dashboard), it is a wish, so every row names its check.

## How to use this file
- Before adding a prompt, a model call, a vendor or an AI-written table: read the rows that apply.
- Before changing a prompt or the model: see G5.
- The automated checks live in `TODO/governance_checks/` and run with `TODO command`. They call no
  provider and need no keys.

## Answers from the start-of-project questionnaire
TODO: providers and tier; personal data in prompts (and which vendors are cleared); outside text in
prompts; customer-facing output; stored facts; actions the model can trigger; spend and limits;
background or interactive; where the team's tests live.

## Controls
"Today" is verified in the code on YYYY-MM-DD. Mark each row Met, Partly met or Gap, and be plain
about what is missing. Delete rows that do not apply and say why under "Skipped".

| # | Rule | Today | Check |
|---|---|---|---|
| G1 | **Personal data only goes to vendors cleared for it.** | TODO | TODO |
| G2 | **Outside text is data, never instructions.** | TODO | TODO |
| G3 | **Every factual claim traces to supplied evidence.** | TODO | TODO |
| G4 | **A person decides; the model never approves its own work.** | TODO | TODO |
| G5 | **Prompt or model changes come with an eval report.** | TODO | TODO |
| G6 | **One place makes model calls.** | TODO | TODO |
| G7 | **Failures are bounded and visible.** | TODO | TODO |
| G8 | **Cost is measured and capped.** | TODO | TODO |
| G9 | **Every AI-written row records which model and prompt version wrote it.** | TODO | TODO |
| G10 | **Production switches are decided in advance.** | TODO | TODO |

## Skipped on purpose
TODO: each control not used, with the reason.

## Production switches (G10)
| Switch | Turn it on when | How |
|---|---|---|
| Prompt caching | Paid, and the usage report shows large repeated prompt starts | TODO |
| Parallel model calls | Higher limits, or jobs slower than target | TODO |
| Batch mode | A scheduled job that can wait exists, and billing is paid | TODO |
| Model routing | An eval report shows a cheaper model matches | TODO |
| Tracing platform | Debugging needs more than the usage table | TODO |
| Spending ceiling and alerts | Paid key | TODO |

## Vendors
| Vendor | Used for | Personal data allowed | Terms status |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

## Not verified
TODO: anything stated here that was not checked (a price from a summary, a model an alias points
to, a screen not opened).
