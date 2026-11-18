import { useState } from "react";

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

// What we could offer this company as a whole, checked against what the research found. The
// offerings the rep picked come first and always show a verdict (even a weak one, or "not checked
// yet"), then the best of the rest, then everything else folded away. Each fit can start a brief.
export function OfferIdeas({
  companyName,
  fit,
  chosen,
  onBriefAround,
}: {
  companyName: string | null;
  fit: OfferingFit[] | null;
  // The offerings picked in the filter above.
  chosen: { id: string; name: string }[];
  onBriefAround: (productId: string) => Promise<void>;
}) {
  const [creating, setCreating] = useState<string | null>(null);
  const all = fit ?? [];
  const byId = new Map(all.map((f) => [f.product_id, f]));
  const chosenIds = new Set(chosen.map((c) => c.id));
  const rest = all.filter((f) => !chosenIds.has(f.product_id));
  const { fits, others } = splitFit(rest);
  const researched = all.length > 0;

  async function create(productId: string) {
    setCreating(productId);
    try {
      await onBriefAround(productId);
    } finally {
      setCreating(null);
    }
  }

  function row(
    key: string,
    name: string,
    f: OfferingFit | undefined,
    picked: boolean,
  ) {
    return (
      <li key={key} className="rounded-xl border border-border p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold">{name}</span>
            {f ? (
              <StatusTag tone={BAND_TONE[f.band]}>
                {BAND_LABEL[f.band]}
              </StatusTag>
            ) : (
              <StatusTag tone="neutral">Not checked yet</StatusTag>
            )}
            {picked && (
              <span className="text-xs text-muted-foreground">You picked</span>
            )}
          </div>
          {f && f.band !== "insufficient_evidence" && (
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
          )}
        </div>
        {f && <p className="mt-1 text-sm">{f.reasoning}</p>}
        {f?.evidence.slice(0, 2).map((e) => (
          <EvidenceQuote
            key={`${e.content_hash}-${e.quote}`}
            quote={e.quote}
            kind={e.kind}
            date={e.date}
            url={e.url}
          />
        ))}
      </li>
    );
  }

  const company = companyName ?? "this company";
  return (
    <Card className="mb-4">
      <CardContent className="flex flex-col gap-4">
        <div className="min-w-0">
          <h2 className="text-lg font-bold">What we could offer {company}</h2>
          <p className="text-sm text-muted-foreground">
            {researched
              ? "Every one of our offerings, checked against what the research found."
              : "Run the research above and each of our offerings is checked against what is found."}
          </p>
        </div>

        {chosen.length > 0 && (
          <section
            aria-label="Offerings you picked"
            className="flex flex-col gap-2"
          >
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Your picks
            </h3>
            <ul className="flex flex-col gap-3">
              {chosen.map((c) => row(c.id, c.name, byId.get(c.id), true))}
            </ul>
          </section>
        )}

        {researched && (
          <section aria-label="Best fits" className="flex flex-col gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {chosen.length > 0 ? "Other offerings that fit" : "Best fits"}
              {fits.length > 0 ? ` (${fits.length})` : ""}
            </h3>
            {fits.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing else found points clearly to one of our offerings yet.
                That is not proof there is no need: try an area above to look
                closer.
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {fits.map((f) => row(f.product_id, f.product_name, f, false))}
              </ul>
            )}
          </section>
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
