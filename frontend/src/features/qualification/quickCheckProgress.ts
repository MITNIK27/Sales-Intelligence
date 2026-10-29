import type { JobProgress } from "@/api/types";

export type StepState = "done" | "current" | "waiting";

// The steps a Quick Check goes through, in order. With a focus there is an extra step to look for
// evidence about it, matching what the job reports.
export function quickCheckSteps(focus: string | null): string[] {
  return [
    "Finding the website and company info",
    ...(focus ? [`Looking for evidence about ${focus}`] : []),
    "Judging fit against your criteria",
  ];
}

export function stepStates(stepCount: number, progress: JobProgress | null): StepState[] {
  const done = Math.min(progress?.done ?? 0, stepCount);
  return Array.from({ length: stepCount }, (_, index) =>
    index < done ? "done" : index === done ? "current" : "waiting",
  );
}

// "1:05" style clock for the running check; never negative if the server clock is ahead.
export function elapsedLabel(startMs: number, nowMs: number): string {
  const seconds = Math.max(0, Math.floor((nowMs - startMs) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}
