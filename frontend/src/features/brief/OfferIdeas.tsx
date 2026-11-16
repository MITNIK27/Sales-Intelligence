import { useState } from "react";
import { Loader2 } from "lucide-react";

import type { OfferingFit } from "@/api/types";
import { StatusTag } from "@/components/StatusTag";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { BAND_LABEL, splitFit } from "@/features/brief/opportunityLabels";
import { EvidenceQuote } from "@/features/quicklook/EvidenceQuote";

const BAND_TONE = {
  strong: "good",
  potential: "watch",
  weak: "neutral",
  insufficient_evidence: "neutral",
} as const;

// What we could offer this company as a whole: researched from its news, hiring and work in the
// areas we sell in, with every offering checked against what was found. Each offering that fits
// can start a brief of its own.
export function OfferIdeas({
  fit,
  finding,
  onFind,
  onBriefAround,
}: {
  fit: OfferingFit[] | null;
  finding: boolean;
  onFind: () => void;
  onBriefAround: (productId: string) => Promise<void>;
}) {
  const [creating, setCreating] = useState<string | null>(null);
  const { fits, others } = splitFit(fit ?? []);
  const researched = (fit ?? []).length > 0;

  async function create(productId: string) {
    setCreating(productId);
    try {
      await onBriefAround(productId);
    } finally {
      setCreating(null);
    }
  }

  return (
    <Card className="mb-4">
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-bold">What we could offer</h2>
            <p className="text-sm text-muted-foreground">
              We look at their recent news, open jobs and work in the areas we
              sell in, then check every one of our offerings against what we
              find.
            </p>
          </div>
          <Button
            variant={researched ? "outline" : "default"}
            disabled={finding}
            onClick={onFind}
          >
            {finding && <Loader2 className="animate-spin" aria-hidden="true" />}
            {finding
              ? "Researching…"
              : researched
                ? "Research again"
                : "Research what we could offer"}
          </Button>
        </div>
        {finding && (
          <p role="status" className="text-sm text-muted-foreground">
            This usually takes about a minute. You can keep using the page.
          </p>
        )}

        {researched && fits.length === 0 && !finding && (
          <p className="text-sm text-muted-foreground">
            Nothing found points clearly to one of our offerings yet. That is
            not proof there is no need: try an area above to look closer.
          </p>
        )}

        {fits.length > 0 && (
          <ul className="flex flex-col gap-3">
            {fits.map((f) => (
              <li
                key={f.product_id}
                className="rounded-xl border border-border p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-x-3">
                    <span className="font-semibold">{f.product_name}</span>
                    <StatusTag tone={BAND_TONE[f.band]}>
                      {BAND_LABEL[f.band]}
                    </StatusTag>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={creating !== null}
                    onClick={() => void create(f.product_id)}
                  >
                    {creating === f.product_id
                      ? "Creating…"
                      : "Create a brief around this"}
                  </Button>
                </div>
                <p className="mt-1 text-sm">{f.reasoning}</p>
                {f.evidence.slice(0, 2).map((e) => (
                  <EvidenceQuote
                    key={`${e.content_hash}-${e.quote}`}
                    quote={e.quote}
                    kind={e.kind}
                    date={e.date}
                    url={e.url}
                  />
                ))}
              </li>
            ))}
          </ul>
        )}

        {others.length > 0 && (
          <details className="text-sm text-muted-foreground">
            <summary className="cursor-pointer">
              {others.length} other offering{others.length === 1 ? "" : "s"}{" "}
              with a weak or no clear link
            </summary>
            <ul className="mt-2 flex flex-col gap-1">
              {others.map((o) => (
                <li key={o.product_id}>
                  {o.product_name}: {BAND_LABEL[o.band]}
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
