import { EyeOff, Quote } from "lucide-react";

import type { DocumentDetailData, KnowledgeCardInfo } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  CARD_KIND_LABEL,
  CONFIDENCE_LABEL,
  summaryWrittenBy,
} from "@/features/documents/documentLabels";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

// What a model wrote about the document: a summary, a summary per section, and knowledge cards
// (short facts, each with the words of the passage it was checked against). A wrong card is
// hidden, never edited, so what is shown is always the model's own words.
export function SummaryTab({
  detail,
  working,
  onHide,
  onSummarise,
  onRefresh,
}: {
  detail: DocumentDetailData;
  working: boolean;
  onHide: (card: KnowledgeCardInfo, hidden: boolean) => void;
  onSummarise: () => void;
  onRefresh: () => void;
}) {
  const sections = detail.sections ?? [];
  const cards = detail.cards ?? [];
  const writtenBy = summaryWrittenBy(detail);

  if (!detail.summary) {
    return (
      <div className="flex flex-col items-start gap-3 text-sm">
        <p className="text-muted-foreground">
          {detail.can_summarise
            ? "No summary yet. It is written in the background after the document is read, and can take a minute."
            : "Summaries and knowledge cards are switched off, or this document has not been read yet."}
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="action" onClick={onRefresh}>
            Check again
          </Button>
          {detail.can_summarise && (
            <Button
              type="button"
              variant="action"
              disabled={working}
              onClick={onSummarise}
            >
              Summarise now
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 text-sm">
      <section aria-label="Summary" className="flex flex-col gap-1">
        <p>{detail.summary}</p>
        <p className="text-xs text-muted-foreground">
          {writtenBy ?? "Written by a model"}
          {detail.summarised_at && ` · ${timeAgo(detail.summarised_at)}`}
        </p>
        {sections.length > 0 && (
          <details className="mt-1 text-xs">
            <summary className="cursor-pointer text-primary-text hover:underline">
              Summary of each part ({sections.length})
            </summary>
            <ul className="mt-2 flex flex-col gap-2 border-l-2 border-border pl-3">
              {sections.map((s) => (
                <li key={s.position}>
                  <span className="font-semibold">{s.locator}: </span>
                  {s.text}
                </li>
              ))}
            </ul>
          </details>
        )}
        {detail.can_summarise && (
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              variant="action"
              disabled={working}
              onClick={onSummarise}
            >
              Summarise again
            </Button>
            <Button type="button" variant="ghost" onClick={onRefresh}>
              Check again
            </Button>
          </div>
        )}
      </section>

      <section aria-label="Knowledge cards" className="flex flex-col gap-2">
        <h3 className="text-sm font-bold">
          Knowledge cards ({cards.filter((c) => !c.hidden).length})
        </h3>
        <p className="text-xs text-muted-foreground">
          Short facts drawn from this document. Each was checked against the
          words of the passage it came from. The flows (best offering, the
          message, suggested areas, Quick Check) see these first. Hide a card
          that is wrong: it is then never used.
        </p>
        {cards.length === 0 ? (
          <p className="text-muted-foreground">
            No facts worth keeping were found in this document.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {cards.map((card) => (
              <CardRow
                key={card.id}
                card={card}
                working={working}
                onHide={onHide}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function CardRow({
  card,
  working,
  onHide,
}: {
  card: KnowledgeCardInfo;
  working: boolean;
  onHide: (card: KnowledgeCardInfo, hidden: boolean) => void;
}) {
  const meta = [
    card.offering?.name,
    card.client,
    card.industry,
    CONFIDENCE_LABEL[card.confidence],
  ].filter(Boolean);
  return (
    <li
      className={cn(
        "flex items-start gap-3 border border-border bg-card p-3",
        card.hidden && "opacity-60",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="bg-secondary px-2 py-0.5 text-xs font-semibold">
            {CARD_KIND_LABEL[card.kind]}
          </span>
          {card.hidden && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground">
              <EyeOff className="size-3" aria-hidden="true" />
              Hidden from every flow
            </span>
          )}
        </div>
        <p className={cn("mt-1", card.hidden && "line-through decoration-1")}>
          {card.statement}
        </p>
        {meta.length > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            {meta.join(" · ")}
          </p>
        )}
        <p className="mt-2 flex gap-1.5 text-xs text-muted-foreground">
          <Quote className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-semibold">{card.locator}:</span> “{card.quote}
            ”
          </span>
        </p>
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={working}
        onClick={() => onHide(card, !card.hidden)}
      >
        {card.hidden ? "Show" : "Hide"}
      </Button>
    </li>
  );
}
