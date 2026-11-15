import { Sparkles } from "lucide-react";

import type { CompanyOpportunity } from "@/api/types";
import { Button } from "@/components/ui/button";
import { titleCaseArea } from "@/features/brief/startBrief";

// AI recommended areas: one button asks for areas worth researching, based on what the company is
// doing and what we can help with. Each recommendation is a chip; choosing one researches it. The
// other two ways in stay in the bar above: pick an area already in the list, or type your own.
export function SuggestedAreas({
  suggested,
  suggesting,
  onSuggest,
  onChoose,
}: {
  suggested: CompanyOpportunity[];
  suggesting: boolean;
  // `refresh` is true when suggestions already exist: the model is asked again.
  onSuggest: (refresh: boolean) => void;
  onChoose: (areaLabel: string) => void;
}) {
  return (
    <div className="mb-4 flex flex-col gap-2">
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
              ? "Refresh AI Recommendations"
              : "AI Recommended Areas"}
        </Button>
        {suggested.length > 0 ? (
          <p className="text-sm text-muted-foreground">
            Pick one to research it, choose an area from the list above, or add
            your own.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            Areas where this company shows activity and we can help.
          </p>
        )}
      </div>
      {suggested.length > 0 && (
        <ul
          aria-label="AI recommended areas"
          className="flex flex-wrap gap-2"
        >
          {suggested.map((o) => (
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
      )}
    </div>
  );
}
