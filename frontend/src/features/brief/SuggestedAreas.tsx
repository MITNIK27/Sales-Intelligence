import { Sparkles } from "lucide-react";

import type { CompanyOpportunity } from "@/api/types";
import { Button } from "@/components/ui/button";
import { titleCaseArea } from "@/features/brief/startBrief";

type Source = NonNullable<CompanyOpportunity["suggestion_source"]> | "other";

// The order the groups are read in: what was searched for first, then what the evidence points to
// near it, then the next best areas elsewhere.
const GROUPS: { source: Source; heading: string }[] = [
  { source: "searched", heading: "Searched in your Market Discovery" },
  { source: "evidence", heading: "From the evidence" },
  { source: "next_best", heading: "Next best areas" },
  { source: "other", heading: "Suggested" },
];

export function groupSuggested(
  suggested: CompanyOpportunity[],
): { heading: string; areas: CompanyOpportunity[] }[] {
  return GROUPS.map((g) => ({
    heading: g.heading,
    areas: suggested.filter(
      (o) => (o.suggestion_source ?? "other") === g.source,
    ),
  })).filter((g) => g.areas.length > 0);
}

// AI recommended areas, the one place to ask for areas worth researching. The first group is what
// the company was searched for in Market Discovery (when it came from a search), then areas the
// evidence supports near it, then the next best ones. Each is a chip; choosing one researches it.
// The other two ways in stay in the bar above: pick an area already in the list, or type your own.
export function SuggestedAreas({
  suggested,
  suggesting,
  notice,
  onSuggest,
  onChoose,
}: {
  suggested: CompanyOpportunity[];
  suggesting: boolean;
  // One sentence about what the last look did, or why it found nothing new.
  notice: string | null;
  // `refresh` is true when suggestions already exist: the model is asked again.
  onSuggest: (refresh: boolean) => void;
  onChoose: (areaLabel: string) => void;
}) {
  const groups = groupSuggested(suggested);
  return (
    <div className="mb-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="action"
          disabled={suggesting}
          onClick={() => onSuggest(suggested.length > 0)}
        >
          <Sparkles className="size-4" aria-hidden="true" />
          {suggesting
            ? "Looking…"
            : suggested.length > 0
              ? "Refresh AI recommendations"
              : "AI recommended areas"}
        </Button>
        <p className="text-sm text-muted-foreground">
          {suggested.length > 0
            ? "Pick one to research it, choose an area from the list above, or add your own."
            : "Starts with what you searched for, then areas where this company shows activity and we can help."}
        </p>
      </div>
      {notice && !suggesting && (
        <p
          role="status"
          className="border-l-2 border-border pl-3 text-sm text-muted-foreground"
        >
          {notice}
        </p>
      )}
      {groups.map((group) => (
        <section key={group.heading} aria-label={group.heading}>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {group.heading}
          </h3>
          <ul className="flex flex-wrap gap-2">
            {group.areas.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  onClick={() => onChoose(o.area_label)}
                  title={o.suggestion_reason ?? undefined}
                  className="flex max-w-sm flex-col items-start gap-0.5 border border-foreground/25 bg-card px-3 py-2 text-left shadow-xs hover:border-primary hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary"
                >
                  <span className="text-sm font-semibold">
                    {titleCaseArea(o.area_label)}
                  </span>
                  {o.suggestion_reason && (
                    <span className="line-clamp-2 text-xs text-muted-foreground">
                      {o.suggestion_reason}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
