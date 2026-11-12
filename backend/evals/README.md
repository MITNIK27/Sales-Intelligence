# Evals

Measures whether the model's answers are good, so a prompt or model change can be judged on
numbers instead of by eye (docs/ai-governance.md, G5). Cases use frozen inputs, so a changed result
means the prompt or the model changed, not the web.

**Rules**
- Evals call the real models, so they are never part of `pytest` and never run on their own. A
  person runs them on purpose (runner: Phase 3, step 3). Tests of the harness itself live in
  `governance_checks/` and use no keys.
- Code grades first: schema, citations really in the evidence, no figure the input did not contain,
  no claim a hostile page planted. A model as judge only where code cannot decide.
- The injection cases check for the *claims* a hostile page planted ("hiring 50 cloud engineers"),
  not for the wording of its instruction, so a model that says "this page tried to give me
  instructions" is not failed for describing the attempt. A model that quotes the planted claim
  while refusing it can still be flagged: read the failure detail before deciding.

**Layout**
- `cases/*.jsonl`: one case per line.
- `reports/`: one JSON report per task, prompt version and model, committed so changes show as diffs.
- `run.py`: the command you run. `runner.py`: runs the cases and builds the report.
- `tasks.py`: for each task, how to call the real code on a frozen input and how to grade it.
- `cases.py`, `graders.py`, `report.py`: loading, checks and reports. Nothing here calls a model.
- `export_offering_cases.py`: turns offering proposals a person approved into cases.

**A case**
```json
{"id": "quicklook-injection-01", "task": "quicklook", "tags": ["injection"],
 "input": {"name": "...", "domain": "...", "evidence": [], "offerings": []},
 "expect": {"call_not_in": ["yes"], "max_strong_offerings": 0},
 "note": "why this case exists"}
```
- `tags`: `injection` (hostile text must not steer the answer), `grounding` (only claim what the
  input supports), `accuracy` (compare with a label a person decided).
- `expect` must not be empty, or the case could never fail. A key the task does not understand is
  rejected when the cases are loaded, so a typo cannot quietly turn a check off.

**What each task's `expect` understands**

| Task | Input needs | Expectations |
|---|---|---|
| `quicklook` | `name`, `domain`, `evidence` (label, url, kind, text, date), `offerings` (label, name, description) | `call_in`, `call_not_in`, `max_strong_offerings`, `no_leak` |
| `qualification` | `company`, `criteria` (name, description, is_disqualifying), optional `signals` | `verdicts` (name to verdict), `verdicts_not` (name to forbidden verdicts), `quotes_valid`, `no_leak` |
| `draft` | `company`, `contact` (first_name, role_title, seniority), `product`, optional `evidence.signals` | `no_unsupported_claims`, `max_words`, `no_leak` |
| `offering_extraction` | `url`, `text` | `is_offering`, `kind`, `name_contains`, `no_figures`, `no_leak` |
| `recommendation` | `company`, `product`, optional `contact_titles`, `signals`, `opportunity_context` | `no_unsupported_claims`, `talking_points_between` (`[low, high]`), `no_leak` |
| `opportunity_assessment` | `company`, `area_label`, `evidence` (signal_type, text, date), optional `industry_context` | `verdict_in`, `verdict_not_in`, `min_findings`, `max_findings`, `max_dropped`, `no_leak` |
| `offering_fit` | `company`, `area_label`, `evidence`, `offerings` (name, description, kind, buyer_profile) | `fits` (offerings that must cite verified evidence), `no_fit` (offerings that must cite none), `max_dropped`, `no_leak` |
| `contact_relevance` | `company`, `area_label`, `contacts` (id, role_title, seniority), optional `product` | `roles_in` (id to allowed roles), `roles_not` (id to forbidden roles), `no_leak` |
| `role_relevance` | `company`, `contacts` (id, role_title, seniority), `categories` (name, description, is_primary_target) | `matches` (id to category name or null), `matches_not`, `all_answered`, `no_leak` |

The last five run the app's own prompt and its own checks on frozen evidence. An answer's citations
are verified exactly as the app verifies them, so a citation that is not in the evidence counts as
dropped, never as support.

**Cases the repository starts with.** 37 hand-written cases (injection, grounding, and a few
"obvious label" accuracy sanity checks). The accuracy cases here are deliberately easy. They do not
replace labels from real companies.

**A new task has no report until you run it.** The G5 check lets a task wait in
`AWAITING_FIRST_REPORT` (in `governance_checks/test_prompt_version_has_eval_report.py`) until its
first report is committed. Run `python -m evals.run --task <task> --yes`, commit the report, and
take the task off that list: the check fails if you forget.

**Adding your own accuracy cases.** An accuracy case is only as good as its label.

*The easy way, for people who are not engineers:* fill in the spreadsheets in `labels/` (guide in
`labels/README.md`) for qualification, role relevance and contact relevance, then run
`python -m evals.import_labels` (a dry run that checks every row) and `--yes` to write the cases.

*By hand:* put them in `cases/accuracy_<task>.jsonl`, one per line, in the shapes above.
- Write the label from what a salesperson would decide using only the frozen input, and say why in
  `note`. Two people disagreeing on a case is useful: keep it and decide together.
- Aim for 20 to 30 per task, with some that should come out "no" or "could not determine", not only
  clear yes cases.
- Qualification example:
  `{"id": "qualification-accuracy-10", "task": "qualification", "tags": ["accuracy"],
  "input": {"company": {"name": "...", "description": "..."}, "criteria": [{"name": "..."}]},
  "expect": {"verdicts": {"<criterion name>": "met"}}, "note": "..."}`

**Running** (from `backend/`, venv active, keys in `backend/.env`). Nothing is called until you add
`--yes`; without it the command prints its plan and stops.
```
python -m evals.run --task quicklook                  # plan only
python -m evals.run --task quicklook --yes            # run it, write a report
python -m evals.run --all --yes                       # every task
python -m evals.run --task draft --tag injection --yes
python -m evals.run --task quicklook --case quicklook-injection-01 --yes
python -m evals.run --task quicklook --repeat 3 --yes   # each case 3 times; shows flaky ones
python -m evals.run --task quicklook --gemini-model <other model> --yes   # try another model
python -m evals.run --task offering_extraction --llm-order gemini --yes   # force a vendor
```
- Each task uses the model the app uses for it (Quick Look: Gemini first; offerings importer:
  Groq first; qualification and drafts: Gemini) and only the first vendor, so every answer in a
  report comes from one model. `--fallback` runs the whole chain like the app does.
- Cases run one at a time with a 3 second pause (`--delay`), because the free tiers limit calls per
  minute. A failed call is an error on that case, not a crash.
- Output shows passes by tag, the calls and estimated cost, each failing case with the answer, and
  what changed since the previous report. The report is written to `reports/` (`--no-write` skips).
- Usage is counted in memory and never written to the database.
- `--repeat N` (1 to 10) runs every case N times and records how many runs passed. A case counts as
  passed only if every run passed; one that passes some runs is reported as flaky. Use it before
  deciding whether a failing case is broken or just varies, and before comparing two models. It
  multiplies the calls, so the plan line shows the run count.
- To compare models, run the same task with `--gemini-model` or `--llm-order` and read the two
  reports side by side.

**Exporting past offering reviews** (read-only, dry run by default, from `backend/`):
`python -m evals.export_offering_cases` shows what would be written; add `--yes` to write
`cases/offering_approved.jsonl`. Rejected proposals are skipped because a rejection does not say
why. Look at the file before committing it: it contains text from website pages.
