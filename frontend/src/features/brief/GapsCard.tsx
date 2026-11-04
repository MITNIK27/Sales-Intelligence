import type { CompanyOpportunity } from "@/api/types";
import { dedupeGaps } from "@/features/brief/opportunityLabels";
import { researchLines } from "@/features/brief/researchLines";

// What was looked for and not found, and what was searched. A gap reads as "we looked and found
// nothing", never as silence, so a rep knows what to ask the customer instead.
export function GapsBody({ opportunity }: { opportunity: CompanyOpportunity }) {
  const gaps = dedupeGaps(opportunity.assessment?.not_found ?? []);
  const lines = researchLines(opportunity.research);
  return (
    <>
      {gaps.length > 0 && (
        <ul className="mb-4 list-inside list-disc text-sm">
          {gaps.map((gap) => (
            <li key={gap}>{gap}</li>
          ))}
        </ul>
      )}
      {lines.length > 0 && (
        <>
          <h3 className="mb-1 text-sm font-bold">What was checked</h3>
          <ul className="list-inside list-disc text-sm text-muted-foreground">
            {lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
