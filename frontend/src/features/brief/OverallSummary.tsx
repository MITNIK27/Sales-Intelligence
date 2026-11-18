import { Loader2 } from "lucide-react";

import type { CompanyOpportunity } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { hasGaps } from "@/features/brief/briefSections";
import { FindingsList } from "@/features/brief/FindingsList";
import { GapsBody } from "@/features/brief/GapsCard";

// The company as a whole, at the top of the Overall view: a short written summary of what recent
// news, open jobs and their website say, each finding quoted. It also holds the one button that runs
// the research, so there is a single obvious place to start it.
export function OverallSummary({
  opportunity,
  companyName,
  chosenNames,
  finding,
  notice,
  onFind,
}: {
  opportunity: CompanyOpportunity;
  companyName: string | null;
  // Offerings picked in the filter, named so the pick has a visible effect.
  chosenNames: string[];
  finding: boolean;
  notice: string | null;
  onFind: () => void;
}) {
  const name = companyName ?? "This company";
  const written = opportunity.assessment !== null;
  const picked = chosenNames.length > 0;

  return (
    <Card className="mb-4">
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-bold">{name} as a whole</h2>
            <p className="text-sm text-muted-foreground">
              {written
                ? "What recent news, open jobs and their website say, each with the words it comes from."
                : "Not written yet. Research reads their recent news, open jobs and website, then writes a short summary with its sources and checks every one of our offerings against it."}
            </p>
            {picked && (
              <p className="mt-1 text-sm">
                Picked in the filter:{" "}
                <span className="font-semibold">{chosenNames.join(", ")}</span>.
                Research looks for signs they need{" "}
                {chosenNames.length === 1 ? "it" : "these"}; the other offerings
                are checked too.
              </p>
            )}
          </div>
          <Button
            variant={written ? "outline" : "default"}
            disabled={finding}
            onClick={onFind}
          >
            {finding && <Loader2 className="animate-spin" aria-hidden="true" />}
            {finding
              ? "Researching…"
              : written
                ? "Research again"
                : `Research ${companyName ?? "this company"}`}
          </Button>
        </div>
        {finding && (
          <p role="status" className="text-sm text-muted-foreground">
            This usually takes about a minute. You can keep using the page.
          </p>
        )}
        {notice && !finding && (
          <p role="status" className="text-sm text-muted-foreground">
            {notice}
          </p>
        )}
        {written && <FindingsList opportunity={opportunity} />}
        {written && hasGaps(opportunity) && (
          <details className="text-sm">
            <summary className="cursor-pointer font-medium text-muted-foreground">
              What we could not find, and what was checked
            </summary>
            <div className="mt-3">
              <GapsBody opportunity={opportunity} />
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
