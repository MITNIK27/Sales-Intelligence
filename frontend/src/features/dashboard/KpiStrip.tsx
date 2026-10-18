import type { DashboardKpis } from "@/api/types";
import { Skeleton } from "@/components/Skeleton";
import { StatTile } from "@/features/dashboard/StatTile";
import { formatNumber } from "@/lib/format";

const GRID = "grid grid-cols-2 gap-4 xl:grid-cols-4";

// Four numbers answer "how did it go": companies found, how many fit, who we can contact, and what
// is waiting in drafts. Everything else lives one click away or in the usage row.
export function KpiStrip({
  kpis,
  scope,
}: {
  kpis: DashboardKpis | null;
  scope: "all" | "search";
}) {
  if (!kpis) {
    return (
      <div className={GRID}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-[116px] border border-border bg-card px-5 py-4"
          >
            <Skeleton className="h-4 w-24" />
            <Skeleton className="mt-3 h-8 w-14" />
            <Skeleton className="mt-3 h-4 w-28" />
          </div>
        ))}
      </div>
    );
  }
  const countedOnce =
    scope === "all"
      ? "A company found by several searches is counted once."
      : "Counted for this search's companies.";
  return (
    <div className={GRID}>
      <StatTile
        label="Companies found"
        value={formatNumber(kpis.companies)}
        note="discovered and checked"
        to="/companies"
        hint={countedOnce}
      />
      <StatTile
        label="Fit your needs"
        value={formatNumber(kpis.fit)}
        note={
          kpis.needs_closer_look > 0
            ? `+${formatNumber(kpis.needs_closer_look)} need a closer look`
            : "meet your requirements"
        }
        to="/companies"
        hint="Companies that meet your requirements. The others need a closer look because a requirement could not be verified."
      />
      <StatTile
        label="Contacts"
        value={formatNumber(kpis.contacts)}
        note={`${formatNumber(kpis.likely_decision_makers)} decision-makers`}
        hint="People found for these companies. Decision-makers are the ones likely to own the decision."
      />
      <StatTile
        label="Drafts to review"
        value={formatNumber(kpis.drafts_to_review)}
        note={`${formatNumber(kpis.drafts_sent)} sent`}
        to="/drafts"
        hint={`Drafts written for these companies' contacts. ${countedOnce}`}
      />
    </div>
  );
}
