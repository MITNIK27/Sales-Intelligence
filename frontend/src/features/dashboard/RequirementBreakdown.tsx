import { useState } from "react";

import type { DashboardRequirement } from "@/api/types";
import { SkeletonLines } from "@/components/Skeleton";
import { requirementShares } from "@/features/dashboard/metrics";
import { MetricBar, StatusCount } from "@/features/dashboard/parts";
import { plural } from "@/lib/format";

const VISIBLE = 4;

// Each requirement a company was judged against, as one bar and three counts (✓ meets, ? couldn't
// verify, ✗ doesn't meet), plus how many drafts exist for the ones that meet it. Where the
// requirement came from and whether it is a must-have is on hover and a small "Must" tag.
export function RequirementBreakdown({
  requirements,
}: {
  requirements: DashboardRequirement[] | null;
}) {
  const [showAll, setShowAll] = useState(false);
  if (requirements === null) return <SkeletonLines lines={4} />;
  if (requirements.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No requirements checked yet. Add some when you confirm a search.
      </p>
    );
  }
  const shown = showAll ? requirements : requirements.slice(0, VISIBLE);
  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-4">
        {shown.map((req) => {
          const shares = requirementShares(req);
          return (
            <li
              key={`${req.scope}-${req.name}`}
              title={`${req.scope === "run" ? "Set for this search" : "Saved criterion"} · ${
                req.hard ? "must be met" : "nice to have"
              }`}
            >
              <div className="flex items-baseline justify-between gap-3">
                <p className="min-w-0 truncate text-sm">{req.name}</p>
                {req.hard && (
                  <span className="shrink-0 border border-border px-1.5 text-xs text-muted-foreground">
                    Must
                  </span>
                )}
              </div>
              <div className="mt-1.5">
                <MetricBar
                  total={100}
                  label={`${req.meets} meet, ${req.couldnt_verify} could not be verified, ${req.doesnt_meet} do not meet`}
                  segments={[
                    { value: shares.meets, className: "bg-success" },
                    { value: shares.unverified, className: "bg-warning" },
                    { value: shares.fails, className: "bg-destructive" },
                  ]}
                />
              </div>
              <p className="mt-1.5 flex items-center gap-4 text-xs">
                <StatusCount kind="meets" count={req.meets} />
                <StatusCount kind="unverified" count={req.couldnt_verify} />
                <StatusCount kind="fails" count={req.doesnt_meet} />
                {req.drafts_for_meeting > 0 && (
                  <span
                    className="text-muted-foreground"
                    title="Drafts written for companies that meet this requirement"
                  >
                    · {req.drafts_for_meeting}{" "}
                    {plural(req.drafts_for_meeting, "draft")}
                  </span>
                )}
              </p>
            </li>
          );
        })}
      </ul>
      {requirements.length > VISIBLE && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="self-start text-sm text-primary-text hover:underline focus-visible:outline-2 focus-visible:outline-primary"
        >
          {showAll ? "Show fewer" : `+${requirements.length - VISIBLE} more`}
        </button>
      )}
    </div>
  );
}
