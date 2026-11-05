# Evals

Measures whether the model's answers are good, so a prompt or model change can be judged on
numbers instead of by eye (docs/ai-governance.md, G5). Cases use frozen inputs, so a changed result
means the prompt or the model changed, not the web.

**Rules**
- Evals call the real models, so they are never part of `pytest` and never run on their own. A
  person runs them on purpose (runner: coming in Phase 3, step 3). Tests of the harness itself live
  in `governance_checks/` and use no keys.
- Code grades first: schema, citations really in the evidence, no figure the input did not contain,
  no phrase a hostile page planted. A model as judge only where code cannot decide.

**Layout**
- `cases/*.jsonl`: one case per line.
- `reports/`: one JSON report per task, prompt version and model, committed so changes show as diffs.
- `graders.py`, `cases.py`, `report.py`: the harness. Nothing here calls a model.

**A case**
```json
{"id": "quicklook-injection-01", "task": "quicklook", "tags": ["injection"],
 "input": {"...": "frozen evidence, offerings, criteria"},
 "expect": {"call_not_in": ["yes"], "no_leak": ["perfect fit"]},
 "note": "why this case exists"}
```
- `task`: one of `quicklook`, `qualification`, `draft`, `offering_extraction`.
- `tags`: `injection` (hostile text must not steer the answer), `grounding` (only claim what the
  input supports), `accuracy` (compare with a label a person decided).
- `expect` must not be empty, or the case could never fail. Unknown keys are rejected, so a typo is
  caught when the file is loaded and not silently ignored.

**Labelling accuracy cases.** An accuracy case is only as good as its label. Write the label from
what a salesperson would decide, using only the frozen input, and say why in `note`. Two people
disagreeing on a case is useful: keep it, tag the note, and decide together.
