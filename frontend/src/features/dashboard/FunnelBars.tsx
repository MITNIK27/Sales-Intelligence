import type { DashboardFunnelStage } from "@/api/types";
import { SkeletonLines } from "@/components/Skeleton";
import { funnelHint, funnelWidth } from "@/features/dashboard/metrics";
import { MetricBar } from "@/features/dashboard/parts";
import { formatNumber } from "@/lib/format";

// The journey of the companies in plain words: found, checked, worth pursuing, have a contact,
// draft written. One short row per stage; the share of the step before is on hover.
export function FunnelBars({
  stages,
}: {
  stages: DashboardFunnelStage[] | null;
}) {
  if (stages === null) return <SkeletonLines lines={5} />;
  const top = stages[0]?.count ?? 0;
  if (top === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing yet. A search will show how many companies reach each step.
      </p>
    );
  }
  return (
    <ol className="flex flex-col gap-4">
      {stages.map((stage) => (
        <li
          key={stage.key}
          title={funnelHint(
            stage.label,
            stage.count,
            stage.percent_of_previous,
          )}
        >
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span>{stage.label}</span>
            <span className="font-semibold tabular-nums">
              {formatNumber(stage.count)}
            </span>
          </div>
          <div className="mt-1.5">
            <MetricBar
              segments={[
                {
                  value: funnelWidth(stage.count, top),
                  className: "bg-primary",
                },
              ]}
              total={100}
              label={`${stage.label}: ${stage.count} of ${top}`}
            />
          </div>
        </li>
      ))}
    </ol>
  );
}
