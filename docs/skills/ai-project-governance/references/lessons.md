# Lessons from the first project

Things that went wrong, or nearly did, while building these controls. Read the section you are
about to work in.

## Evals

- **Read the app's own thresholds before writing a positive-control case.** A case with 197
  characters of evidence flipped between runs because the app treats anything under 300 characters
  as "too thin to judge". It was testing a code rule, not the model. Add a check that positive
  controls stay above the threshold.
- **A planted sentence is quotable.** If an injected instruction sits in the evidence, a fooled
  model can cite it and pass the app's own "quote must appear in the source" check. Grade the
  answer (the verdict, the band, whether anything verified at all), not only the citation.
- **Pair every skip with a positive control.** A prompt too cautious to ever say yes passes every
  injection case. Include a case where the right answer is yes, and a fake model that never says yes
  must fail it.
- **Prove each grader can fail.** For every task, a fake model that obeys the planted instruction
  must fail its case and a well-behaved one must pass. Without this a green report means nothing.
- **One run proves little.** A model that varies needs a repeat option and a "flaky" state (some
  runs passed) so broken and flaky are told apart. Pass only if every run passes.
- **Run the evals' own code, not a copy.** When the app's checking logic is buried in a function
  that also touches the database, extract the pure part so the app and the eval share it.
- **Reports can wait, but visibly.** A new task has no report until a person runs it. Allow that
  only through a shrink-only list in the check, so it cannot be forgotten.
- **Do not label by guessing.** Accuracy labels must come from people. Give them spreadsheets and an
  importer that reports mistakes with file and row, not JSON.

## Enforcement

- **Put checks where they are committed.** If the team keeps its test folders local, a check there
  is not a control. Use a separate tracked folder and say so in the governance doc.
- **Show the check failing.** After writing a ratchet, add a deliberate violation, see it fail, and
  remove it. Twice this caught a check that could not fail.
- **Cross-language lists drift.** A list of allowed values in the backend and again in the frontend
  needs a check that reads both and compares them.
- **A rolling model alias hides the model, the behaviour and the price.** Pin a named model once
  the project is past a prototype.

## A "not a fit" or "dismiss" action

- **Enumerate every place that picks work before you ship it.** Marking something dismissed meant
  touching about nine queries (the pipeline, bulk jobs, the review queue, reminders, dashboards, the
  index that reuses past results). A discovery run that finds the same company again must not bring
  it back. Test each pair: one dismissed, one active, so a skip never quietly becomes "skip all".
- **Keep what the system believed when it made the proposal.** A rejection with nothing to compare
  against is a label with no input. Store the evidence and the model's reasoning on the item.
- **Enforce warnings on the server.** A screen can ask before hiding something with real history,
  but a stale screen must not be able to skip it. Refuse with a clear message until the request
  confirms; let the screen call a check endpoint first so it can warn without trying.
- **Log the undo too**, with the reason that was withdrawn.
- **Never put names or emails in a decision log snapshot.** Role and seniority are enough.

## Process

- **A migration and the code that reads it must ship together.** New columns read by every query
  break the app until the migration runs. Say so every time, and never run it for the person.
- **Prefer small commits named by phase.** "Phase 2 (1/2)" tells a reviewer what to expect.
- **Check provider facts at the source.** A price from a summary is not confirmed. Read the
  vendor's own page, and record what could not be verified (here, which model an alias points to).
- **Type errors can hide real bugs.** Fixing a backlog of old type errors found a place that deleted
  a record before checking its replacement existed.
- **A flaky test seen once is still worth writing down.** Say it happened and that it could not be
  reproduced; do not call the suite green without saying so.
