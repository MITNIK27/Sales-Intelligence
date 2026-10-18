import { Check, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import type { JobStatus } from "@/api/types";

const STAGES = [
  "Find & enrich companies",
  "Check fit",
  "Find decision-makers",
  "Draft for confirmed contacts",
];

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s.toString().padStart(2, "0")}s` : `${s}s`;
}

// What is really happening while the pipeline runs: which of the four stages we are in, how far
// through the companies, and how long it has taken — all from the job's own progress record.
export function RunProgress({ job }: { job: JobStatus }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const progress = job.progress;
  // No progress yet means stage 1 (discovery) has not reported its first company.
  const currentStage = progress?.stage ?? (progress ? Math.min(progress.done + 1, 4) : 1);
  const startedAt = job.started_at ?? job.created_at;
  const elapsed = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
  const stageDone = progress?.stage_done;
  const stageTotal = progress?.stage_total;

  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {STAGES.map((name, index) => {
          const stageNumber = index + 1;
          const finished = stageNumber < currentStage;
          const active = stageNumber === currentStage;
          return (
            <li
              key={name}
              className={
                active
                  ? "flex items-center gap-1 font-semibold"
                  : finished
                    ? "flex items-center gap-1 text-muted-foreground"
                    : "flex items-center gap-1 text-muted-foreground/60"
              }
            >
              {finished ? (
                <Check className="size-3.5 text-primary" />
              ) : active ? (
                <Loader2 className="size-3.5 animate-spin text-primary" />
              ) : (
                <span className="inline-block size-3.5 text-center text-xs">{stageNumber}</span>
              )}
              {name}
            </li>
          );
        })}
      </ol>

      {stageTotal != null && stageDone != null && stageTotal > 0 && (
        <div>
          <div className="h-2 w-full overflow-hidden rounded bg-muted">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${Math.round((stageDone / stageTotal) * 100)}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {stageDone} / {stageTotal}
            {progress?.enriched != null && ` · ${progress.enriched} enriched`}
            {progress?.failed ? ` · ${progress.failed} failed` : ""}
          </p>
        </div>
      )}

      <p className="text-sm">
        {progress?.detail ??
          (job.status === "pending" ? "Waiting for the worker to pick this up…" : "Starting…")}
      </p>
      <p className="text-xs text-muted-foreground">Elapsed {formatElapsed(elapsed)}</p>
    </div>
  );
}
