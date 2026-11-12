# Evals (template)

Measures whether the model's answers are good, so a prompt or model change can be judged on numbers
instead of by eye. Copy `cases.py` and `graders.py` to `evals/` and add the three things below.

**Add these**
1. `tasks.py`: for each task, a function that calls YOUR real code on a frozen input, and a pure
   function that grades the answer. Keep `run` separate from `grade` so grading can be tested with
   canned answers, including a model that was fooled on purpose.
2. `runner.py` and `run.py`: run the cases one after another (free tiers limit calls per minute),
   record failed calls as an error on that case, write a report per task, prompt version and model,
   and print what changed since the previous report. Refuse to call any model without `--yes`. Add
   `--repeat N` so you can tell flaky from broken.
3. `report.py`: a JSON report named `<task>-<prompt_version>-<model>.json`, committed to git.

**Rules**
- Evals call real models, so they are never part of the automatic test run and never run on their
  own. A person runs them on purpose.
- Start with injection and grounding cases: they need no labels. Add accuracy cases from labels a
  person decided, written in a spreadsheet and imported with a checker that reports mistakes by file
  and row.
- For every task, prove with fake models that a model obeying the planted instruction fails and a
  well-behaved one passes, and include a positive control where the right answer is "yes".
- Read the app's own thresholds first, so positive controls test the model and not a code rule.

See `../../references/lessons.md` for the mistakes made building the first set.
