import { useEffect, useState } from "react";
import { Check, Circle, Loader2 } from "lucide-react";

import type { CompanyOpportunity } from "@/api/types";
import { Button } from "@/components/ui/button";
import { titleCaseArea } from "@/features/brief/startBrief";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// The steps shown while an area is researched. They are indicative: the work runs in the
// background and reports only when it is done.
export const RESEARCH_STEPS = [
  "Reading their recent news",
  "Checking their open jobs",
  "Searching the web for what they are doing",
  "Writing up what we found",
] as const;

export function researchStep(seconds: number): number {
  if (seconds < 6) return 0;
  if (seconds < 14) return 1;
  if (seconds < 24) return 2;
  return 3;
}

// A brand new area has nothing to show yet, so it shows only this: what will happen and one button,
// then named steps while it runs. Everything else appears once there is something to say.
export function ResearchCard({
  opportunity,
  companyName,
  researching,
  onResearch,
}: {
  opportunity: CompanyOpportunity;
  companyName: string | null;
  researching: boolean;
  onResearch: () => void;
}) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!researching) return;
    setSeconds(0);
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [researching]);
  const current = researchStep(seconds);

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-bold">
            Research {titleCaseArea(opportunity.area_label)}
          </h2>
          <p className="text-sm text-muted-foreground">
            We look at {companyName ?? "the company"}&rsquo;s recent news, open
            jobs and public web pages for what they are doing in this area, then
            check it against what we sell.
          </p>
        </div>
        {researching ? (
          <div aria-live="polite">
            <ol className="flex flex-col gap-2">
              {RESEARCH_STEPS.map((label, index) => (
                <li
                  key={label}
                  className={cn(
                    "flex items-center gap-2 text-sm",
                    index > current
                      ? "text-muted-foreground"
                      : "text-foreground",
                  )}
                >
                  {index < current ? (
                    <Check
                      className="size-4 text-chip-success-fg"
                      aria-hidden="true"
                    />
                  ) : index === current ? (
                    <Loader2
                      className="size-4 animate-spin text-primary"
                      aria-hidden="true"
                    />
                  ) : (
                    <Circle className="size-4" aria-hidden="true" />
                  )}
                  {label}
                </li>
              ))}
            </ol>
            <p className="mt-3 text-xs text-muted-foreground">
              This usually takes about a minute.
            </p>
          </div>
        ) : (
          <div>
            <Button onClick={onResearch}>Research this area</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
