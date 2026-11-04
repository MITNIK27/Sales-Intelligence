import { useState } from "react";

import type { FitBand, OfferingFit } from "@/api/types";
import { StatusTag, type Tone } from "@/components/StatusTag";
import { Button } from "@/components/ui/button";
import { CompareOfferings } from "@/features/brief/compare/CompareOfferings";
import { BAND_LABEL } from "@/features/brief/opportunityLabels";
import { EvidenceQuote } from "@/features/quicklook/EvidenceQuote";

const BAND_TONE: Record<FitBand, Tone> = {
  strong: "good",
  potential: "watch",
  weak: "neutral",
  insufficient_evidence: "neutral",
};

// Which of our offerings to lead with for this area. Before it is worked out, this is where the
// button lives, so the action sits next to what it produces.
export function BestOffering({
  focus,
  fit,
  working,
  onWorkOut,
}: {
  focus: OfferingFit | null;
  fit: OfferingFit[];
  working: boolean;
  onWorkOut: (force: boolean) => void;
}) {
  const [comparing, setComparing] = useState(false);

  if (!focus) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-muted-foreground">
          Compare our offerings with what the company is doing and name the one
          to lead with.
        </p>
        <Button disabled={working} onClick={() => onWorkOut(false)}>
          {working ? "Working it out…" : "Work out the best offering"}
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-base font-bold">{focus.product_name}</span>
        <StatusTag tone={BAND_TONE[focus.band]}>
          {BAND_LABEL[focus.band]}
          {focus.needs_review ? " · please check" : ""}
        </StatusTag>
      </div>
      <p className="text-sm">{focus.reasoning}</p>
      {focus.evidence.slice(0, 3).map((e) => (
        <EvidenceQuote
          key={`${e.content_hash}-${e.quote}`}
          quote={e.quote}
          kind={e.kind}
          date={e.date}
          url={e.url}
        />
      ))}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={working}
          onClick={() => onWorkOut(true)}
        >
          {working ? "Checking…" : "Check again"}
        </Button>
        {fit.length >= 2 && (
          <Button
            size="sm"
            variant="ghost"
            aria-pressed={comparing}
            onClick={() => setComparing((c) => !c)}
          >
            {comparing ? "Hide comparison" : "Compare with another offering"}
          </Button>
        )}
      </div>
      {comparing && fit.length >= 2 && <CompareOfferings fit={fit} />}
    </div>
  );
}
