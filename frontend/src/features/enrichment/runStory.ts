// The words of the Market Discovery run screen, kept apart from the components so they can be
// checked: what each step is called, what it is doing in plain terms, and what to say when the
// job has not reported a detail yet. "Starting…" is only right before anything has happened.

export const STAGE_TITLES = [
  "Find companies",
  "Check fit",
  "Find people",
  "Drafts (you choose who)",
] as const;

const HEADLINES = [
  "Finding companies that match your search",
  "Checking each company against your criteria",
  "Finding the right people at each company",
  "Almost done",
] as const;

const WHAT_IT_DOES = [
  "Searching the web, then reading each company's website for what it does.",
  "Judging every company against the criteria you chose.",
  "Looking up decision-makers and sorting them by how likely they are to buy.",
  "Nothing is written until you pick a person from the list.",
] as const;

const WAITING = [
  "Searching and reading company websites…",
  "Checking each company against your criteria…",
  "Finding the right people at each company…",
  "Wrapping up…",
] as const;

const clampStage = (stage: number) => Math.min(Math.max(stage, 1), 4);

export const stageHeadline = (stage: number) =>
  HEADLINES[clampStage(stage) - 1];
export const stageExplainer = (stage: number) =>
  WHAT_IT_DOES[clampStage(stage) - 1];

// The sentence for what is happening now: the job's own detail when it sent one, otherwise a
// sentence about the current step. Only a job that is still waiting says "Starting…".
export function currentActivity(
  stage: number,
  detail: string | null | undefined,
  pending: boolean,
): string {
  if (detail) return detail;
  if (pending) return "Waiting for the worker to pick this up…";
  return WAITING[clampStage(stage) - 1];
}

// Newest first, without the line already shown as the current activity, at most four.
export function recentTrail(
  trail: string[] | undefined,
  current: string,
): string[] {
  return [...(trail ?? [])]
    .reverse()
    .filter((line) => line !== current)
    .slice(0, 4);
}

export type RunOutcome = {
  found: number;
  fit: number | null;
  sorted: number | null;
  ready: number | null;
  needAttention: number | null;
};

// "We found 12 companies, and 4 are ready for you to contact."
export function outcomeHeadline(outcome: RunOutcome): string {
  const { found, ready } = outcome;
  const companies = `${found} ${found === 1 ? "company" : "companies"}`;
  if (ready === null) return `We found ${companies}.`;
  if (found === 0) return "We did not find any companies this time.";
  if (ready === 0)
    return `We found ${companies}, but none are ready to contact yet.`;
  return `We found ${companies}, and ${ready} ${ready === 1 ? "is" : "are"} ready for you to contact.`;
}
