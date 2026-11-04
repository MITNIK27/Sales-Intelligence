import { ExternalLink } from "lucide-react";

import type { CompanyOpportunity } from "@/api/types";
import {
  evidenceLine,
  findingKindLabel,
} from "@/features/brief/opportunityLabels";
import { formatDate } from "@/lib/format";
import { safeHref } from "@/lib/safeHref";

// What the company is doing in this area, in its own words: the summary, then each finding with
// the quote it rests on, its date and a link to the source. Nothing here is a claim without a quote.
export function FindingsList({
  opportunity,
}: {
  opportunity: CompanyOpportunity;
}) {
  const a = opportunity.assessment;
  if (!a) return null;
  return (
    <>
      <p className="mb-4 text-base">{a.summary}</p>
      <ul className="flex flex-col divide-y divide-border border-y border-border">
        {a.findings.map((f, i) => {
          const href = safeHref(f.evidence.url);
          return (
            <li
              key={i}
              className="grid gap-1 py-3 sm:grid-cols-[110px_1fr] sm:gap-4"
            >
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground sm:pt-0.5">
                {findingKindLabel(f.kind)}
              </span>
              <div>
                <p className="font-medium">{f.statement}</p>
                <blockquote className="mt-1 border-l-2 border-border pl-3 text-sm text-muted-foreground">
                  “{f.evidence.quote}”
                </blockquote>
                <p className="mt-1 text-xs text-muted-foreground">
                  {f.evidence.date ? formatDate(f.evidence.date) : "Undated"}
                  {href && (
                    <>
                      {" · "}
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-foreground underline underline-offset-2 hover:text-primary-text"
                      >
                        Source{" "}
                        <ExternalLink className="size-3" aria-hidden="true" />
                      </a>
                    </>
                  )}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-muted-foreground">
        {evidenceLine(a.evidence_count, a.findings.length, a.dropped_count)}
      </p>
    </>
  );
}
