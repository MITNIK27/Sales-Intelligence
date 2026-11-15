import { Check, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import type { JobStatus } from "@/api/types";
import {
  STAGE_TITLES,
  currentActivity,
  recentTrail,
  stageExplainer,
  stageHeadline,
} from "@/features/enrichment/runStory";

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s.toString().padStart(2, "0")}s` : `${s}s`;
}

// What is really happening while the pipeline runs, told as a short story: a headline for the
// step, the four steps, how far through this step, the thing being worked on right now, and the
// last few things that really happened. All of it comes from the job's own progress record.
export function RunProgress({ job }: { job: JobStatus }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const progress = job.progress;
  // No progress yet means stage 1 (discovery) has not reported its first company.
  const currentStage =
    progress?.stage ?? (progress ? Math.min(progress.done + 1, 4) : 1);
  const startedAt = job.started_at ?? job.created_at;
  const elapsed = Math.max(
    0,
    Math.floor((now - new Date(startedAt).getTime()) / 1000),
  );
  const stageDone = progress?.stage_done;
  const stageTotal = progress?.stage_total;
  const activity = currentActivity(
    currentStage,
    progress?.detail,
    job.status === "pending",
  );
  const trail = recentTrail(progress?.trail, activity);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-base font-semibold">{stageHeadline(currentStage)}</p>
        <p className="text-sm text-muted-foreground">
          {stageExplainer(currentStage)}
        </p>
      </div>

      <ol className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
        {STAGE_TITLES.map((name, index) => {
          const stageNumber = index + 1;
          const finished = stageNumber < currentStage;
          const active = stageNumber === currentStage;
          return (
            <li
              key={name}
              aria-current={active ? "step" : undefined}
              className={
                active
                  ? "flex items-center gap-1.5 font-semibold"
                  : finished
                    ? "flex items-center gap-1.5 text-muted-foreground"
                    : "flex items-center gap-1.5 text-muted-foreground/60"
              }
            >
              {finished ? (
                <Check className="size-4 text-primary" aria-label="done" />
              ) : active ? (
                <Loader2
                  className="size-4 animate-spin text-primary motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : (
                <span className="inline-block size-4 text-center text-xs">
                  {stageNumber}
                </span>
              )}
              {name}
            </li>
          );
        })}
      </ol>

      {stageTotal != null && stageDone != null && stageTotal > 0 && (
        <div>
          <div
            className="h-2 w-full overflow-hidden bg-muted"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={stageTotal}
            aria-valuenow={stageDone}
          >
            <div
              className="h-full bg-primary transition-all duration-500"
              style={{
                width: `${Math.round((stageDone / stageTotal) * 100)}%`,
              }}
            />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {stageDone} of {stageTotal} in this step
            {progress?.enriched != null && ` · ${progress.enriched} enriched`}
            {progress?.failed ? ` · ${progress.failed} failed` : ""}
          </p>
        </div>
      )}

      <p className="text-base" aria-live="polite">
        {activity}
      </p>

      {trail.length > 0 && (
        <ul
          aria-label="What just happened"
          className="flex flex-col gap-1 border-l-2 border-border pl-3 text-sm text-muted-foreground"
        >
          {trail.map((line, index) => (
            <li key={line} style={{ opacity: 1 - index * 0.2 }}>
              {line}
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-muted-foreground">
        Elapsed {formatElapsed(elapsed)}
      </p>
    </div>
  );
}
