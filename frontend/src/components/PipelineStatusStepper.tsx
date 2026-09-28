import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";

export type PipelineStepStatus = "done" | "pending" | "in_progress" | "attention";

export type PipelineStep = {
  label: string;
  status: PipelineStepStatus;
  detail?: string;
};

const STATUS_ICON: Record<PipelineStepStatus, LucideIcon> = {
  done: CheckCircle2,
  pending: Circle,
  in_progress: Loader2,
  attention: AlertCircle,
};

const STATUS_COLOR: Record<PipelineStepStatus, string> = {
  done: "text-success",
  pending: "text-muted-foreground",
  in_progress: "text-primary",
  attention: "text-destructive",
};

/** Read-only summary of what the automated pipeline (discover → enrich → qualify → classify
 * roles → draft) has done to this specific company so far — no logic of its own, purely
 * reflecting whatever state the caller already has in hand. Exists because the individual
 * per-stage buttons on the company page don't otherwise convey that this is one continuous,
 * mostly-automatic pipeline rather than five unrelated actions.
 *
 * Laid out as a divided grid rather than inline connector lines between flex items — steps have
 * wildly different detail-text lengths (one line vs. two, or none), and a per-item connector
 * anchored to that item's own top edge ends up at a different height for every step, reading as
 * a broken/uneven row. A shared divider between fixed-height cells has no such failure mode. */
export function PipelineStatusStepper({ steps }: { steps: PipelineStep[] }) {
  return (
    <Card className="p-0">
      <div className="grid grid-cols-1 divide-y divide-border sm:grid-cols-5 sm:divide-x sm:divide-y-0">
        {steps.map((step) => {
          const Icon = STATUS_ICON[step.status];
          return (
            <div key={step.label} className="flex flex-col gap-1 p-4">
              <div className="flex items-center gap-2">
                <Icon
                  className={`size-4 shrink-0 ${STATUS_COLOR[step.status]} ${
                    step.status === "in_progress" ? "animate-spin" : ""
                  }`}
                />
                <p className="text-sm font-semibold">{step.label}</p>
              </div>
              {step.detail && (
                <p className="text-xs text-muted-foreground">{step.detail}</p>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
