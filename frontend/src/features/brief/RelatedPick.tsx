import { useState } from "react";

import type { CompanyOpportunity, OfferingFit } from "@/api/types";
import { StatusTag } from "@/components/StatusTag";
import { Button } from "@/components/ui/button";
import { BAND_LABEL } from "@/features/brief/opportunityLabels";
import { titleCaseArea, type BriefTarget } from "@/features/brief/startBrief";
import { EvidenceQuote } from "@/features/quicklook/EvidenceQuote";

const BAND_TONE = {
  strong: "good",
  potential: "watch",
  weak: "neutral",
  insufficient_evidence: "neutral",
} as const;

// An offering picked in the filter that belongs to a different area than the one being read. It is
// never made the lead offering here: it has its own brief. This card says so, shows how it relates
// to this area when that was judged (and why), and goes to its own brief, or starts it.
export function RelatedPick({
  target,
  areaLabel,
  fit,
  ownArea,
  onOpen,
  onStart,
}: {
  target: BriefTarget;
  // The area being read.
  areaLabel: string;
  // How the offering was judged inside this area, if it was.
  fit: OfferingFit | undefined;
  // The offering's own brief, when it exists.
  ownArea: CompanyOpportunity | null;
  onOpen: (areaId: string) => void;
  onStart: () => Promise<void>;
}) {
  const [working, setWorking] = useState(false);
  const own = titleCaseArea(target.areaLabel);
  const here = titleCaseArea(areaLabel);

  async function start() {
    setWorking(true);
    try {
      await onStart();
    } finally {
      setWorking(false);
    }
  }

  return (
    <section
      aria-label={`${target.name}, picked in the filter`}
      className="mb-4 flex flex-col gap-2 border border-border bg-card p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="min-w-0 flex-1 text-sm">
          <span className="font-bold">You picked {target.name}.</span>{" "}
          <span className="text-muted-foreground">
            It has its own brief, &ldquo;{own}&rdquo;. This page is about {here}
            , so {target.name} is not the lead offering here.
          </span>
        </p>
        {ownArea?.assessment ? (
          <Button size="sm" onClick={() => onOpen(ownArea.id)}>
            Open the {own} brief
          </Button>
        ) : (
          <Button size="sm" disabled={working} onClick={() => void start()}>
            {working ? "Opening…" : `Research ${own}`}
          </Button>
        )}
      </div>

      <div className="border-t border-border pt-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          How {target.name} relates to {here}
        </p>
        {fit ? (
          <>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
              <StatusTag tone={BAND_TONE[fit.band]}>
                {BAND_LABEL[fit.band]}
              </StatusTag>
              <span>{fit.reasoning}</span>
            </p>
            {fit.evidence.slice(0, 1).map((e) => (
              <EvidenceQuote
                key={`${e.content_hash}-${e.quote}`}
                quote={e.quote}
                kind={e.kind}
                date={e.date}
                url={e.url}
              />
            ))}
          </>
        ) : (
          <p className="mt-1 text-sm text-muted-foreground">
            Not checked against {here} yet.
          </p>
        )}
      </div>
    </section>
  );
}
