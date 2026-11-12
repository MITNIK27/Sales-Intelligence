# Labelling for accuracy

These files are how the team tells the evals what the right answer is. A model is then measured
against what people decided, not against what we guessed. Fill them in a spreadsheet (Excel, Google
Sheets), save as CSV, and ask an engineer to run the import. The first row of each file is the
header: do not rename or remove columns. Rows whose `case_id` starts with `EXAMPLE` are samples and
are ignored.

**What makes a good label**
- Label what a salesperson would decide, using only what is written in the row. If the row does not
  say, the honest label is `could_not_determine` (or "no match"), not your best guess.
- Include clear no's and "can't tell" cases, not only the easy yes. A model that says yes to
  everything should fail.
- Aim for 20 to 30 cases per file. A case is one company, with one row per question about it.
- Use real companies and real titles from your own work. Do not paste personal details: titles and
  seniority are enough, never names or emails.
- If two people disagree on a label, keep the case and write both views in `why`. Those are the
  cases worth discussing.

**The files**
| File | One row is | `label` / answer |
|---|---|---|
| `qualification_labels.csv` | one criterion for one company | `met`, `not_met` or `could_not_determine` |
| `role_categories.csv` | one of your role categories (copy yours from the app) | `is_primary_target`: yes or no |
| `role_labels.csv` | one contact at a company | `expected_category`: the category name, or blank for none |
| `contact_labels.csv` | one contact for one business area | `expected_roles` and/or `not_roles`: `decision_maker`, `influencer`, `user`, `not_relevant`, separated by `\|` |

Rows with the same `case_id` belong to the same company; the company columns only need to be filled
on the first row (a later row that disagrees is reported as an error). In `qualification_labels.csv`
the optional `evidence` column is one piece of news or text the judgment may use.

**Importing** (from `backend/`, venv active)
```
python -m evals.import_labels          # checks every row and shows what it would write
python -m evals.import_labels --yes    # writes evals/cases/accuracy_<task>.jsonl
```
Any mistake is reported with the file and row, and nothing is written until all of it is right. After
importing, the reports for those tasks are out of date: run
`python -m evals.run --task <task> --repeat 3 --yes` and commit them (the governance check fails
until you do).
