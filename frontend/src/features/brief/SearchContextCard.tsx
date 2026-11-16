import { Loader2 } from "lucide-react";
import { useState } from "react";

import type { SearchContextOffering, SearchContextRun } from "@/api/types";
import { StatusTag } from "@/components/StatusTag";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { titleCaseArea } from "@/features/brief/startBrief";
import { EvidenceQuote } from "@/features/quicklook/EvidenceQuote";

const BAND_TONE = {
  strong: "good",
  potential: "watch",
  weak: "neutral",
  insufficient_evidence: "neutral",
} as const;

function searchedLine(run: SearchContextRun): string {
  const parts = [
    run.searched.industry_keywords.join(", "),
    run.searched.location ? `in ${run.searched.location}` : "",
    run.searched.employee_size_range
      ? `${run.searched.employee_size_range} employees`
      : "",
  ].filter(Boolean);
  return parts.join(" ") || run.label;
}

function date(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      });
}

// What this company was searched for in Market Discovery and what was found, shown as soon as the
// Brief opens so nobody has to run a brief to see it. Each offering searched shows its fit (decided
// by rules from stored evidence), the reasoning and the quotes behind it, or says plainly that it is
// being worked out or has not been checked.
export function SearchContextCard({
  runs,
  onResearch,
  onOpenArea,
}: {
  runs: SearchContextRun[];
  onResearch: (offering: SearchContextOffering) => Promise<void>;
  onOpenArea: (areaId: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [latest, ...older] = runs;
  if (!latest) return null;

  async function research(o: SearchContextOffering) {
    setBusy(o.product_id);
    try {
      await onResearch(o);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="mb-4" aria-label="From your Market Discovery search">
      <CardContent className="flex flex-col gap-3">
        <div>
          <h2 className="text-base font-bold">
            From your Market Discovery search
          </h2>
          <p className="text-sm text-muted-foreground">
            You searched for {searchedLine(latest)}
            {date(latest.created_at) ? ` on ${date(latest.created_at)}` : ""}.
          </p>
          {latest.criteria.length > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              Criteria: {latest.criteria.join("; ")}
            </p>
          )}
        </div>

        {latest.offerings.length > 0 && (
          <p className="text-sm font-semibold">
            {latest.offerings_found_by === "keywords"
              ? "Our offerings that match these words"
              : "Offerings chosen for this search"}
          </p>
        )}

        <ul className="flex flex-col gap-3">
          {latest.offerings.map((o) => (
            <li
              key={o.product_id}
              className="rounded-xl border border-border p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-sm font-semibold">{o.name}</span>
                  {o.state === "judged" && o.band && (
                    <StatusTag tone={BAND_TONE[o.band]}>
                      {o.band_label}
                    </StatusTag>
                  )}
                  {o.state === "working" && (
                    <span
                      role="status"
                      className="flex items-center gap-1 text-sm text-muted-foreground"
                    >
                      <Loader2
                        className="size-4 animate-spin"
                        aria-hidden="true"
                      />
                      Being worked out
                    </span>
                  )}
                  {o.state === "not_checked" && (
                    <StatusTag tone="neutral">Not checked yet</StatusTag>
                  )}
                </div>
                {o.area_researched && o.area_id ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onOpenArea(o.area_id as string)}
                  >
                    Open the {titleCaseArea(o.area_label)} brief
                  </Button>
                ) : o.state !== "working" ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() => void research(o)}
                  >
                    {busy === o.product_id ? "Starting…" : "Research this area"}
                  </Button>
                ) : null}
              </div>
              {o.reasoning && <p className="mt-1 text-sm">{o.reasoning}</p>}
              {o.evidence.map((e) => (
                <EvidenceQuote
                  key={`${e.content_hash ?? ""}-${e.quote}`}
                  quote={e.quote}
                  kind={e.kind ?? null}
                  date={e.date ?? null}
                  url={e.url ?? null}
                />
              ))}
            </li>
          ))}
        </ul>

        {older.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Also found in:{" "}
            {older
              .map((r) => `${searchedLine(r)} (${date(r.created_at)})`)
              .join("; ")}
            .
          </p>
        )}
      </CardContent>
    </Card>
  );
}
