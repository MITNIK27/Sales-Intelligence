import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  outcomeHeadline,
  type RunOutcome as Outcome,
} from "@/features/enrichment/runStory";

const STEPS: { key: keyof Omit<Outcome, "needAttention">; label: string }[] = [
  { key: "found", label: "Companies found" },
  { key: "fit", label: "Companies that fit" },
  { key: "sorted", label: "Companies with people found" },
  { key: "ready", label: "Companies to review" },
];

// How a finished search ended, told in one sentence and one strip that reads left to right:
// companies found, fit, people found, to review. Then the one thing to do next.
export function RunOutcome({
  outcome,
  cappedAt,
  onReview,
  onNewSearch,
}: {
  outcome: Outcome;
  // The number of companies this run takes through role sorting, when it left some out.
  cappedAt: number | null;
  onReview: () => void;
  onNewSearch: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-lg font-semibold">{outcomeHeadline(outcome)}</p>

      <ol className="flex flex-col gap-3 sm:flex-row sm:items-stretch sm:gap-0">
        {STEPS.map((step, index) => {
          const value = outcome[step.key];
          return (
            <li
              key={step.key}
              className="flex items-center sm:flex-1"
              aria-label={`${step.label}: ${value ?? "not available"}`}
            >
              <div className="flex-1 border border-border bg-background px-4 py-3">
                <p className="text-2xl font-bold tabular-nums">
                  {value ?? "–"}
                </p>
                <p className="text-xs text-muted-foreground">{step.label}</p>
              </div>
              {index < STEPS.length - 1 && (
                <ArrowRight
                  className="mx-2 hidden size-4 shrink-0 text-muted-foreground sm:block"
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>

      <p className="text-sm text-muted-foreground">
        {outcome.ready === 0
          ? "Nothing is ready yet. The companies that were left out are listed below with the reason for each."
          : "Pick a company below to see its people and write a draft. Nothing is drafted until you choose."}
        {outcome.needAttention
          ? ` ${outcome.needAttention} ${outcome.needAttention === 1 ? "company needs" : "companies need"} a look.`
          : ""}
      </p>
      {cappedAt !== null && (
        <p className="text-sm text-muted-foreground">
          People were looked up for the top {cappedAt} companies by score only,
          to protect usage limits. The rest are listed below under “not shown”.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" onClick={onReview}>
          Review companies
        </Button>
        <Button type="button" variant="action" onClick={onNewSearch}>
          New search
        </Button>
      </div>
    </div>
  );
}
