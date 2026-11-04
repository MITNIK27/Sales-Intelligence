import { EvidenceQuote } from "@/features/quicklook/EvidenceQuote";
import type { GraphNode, Quote } from "@/features/brief/graph/buildGraph";

function QuoteLine({ q }: { q: Quote }) {
  return (
    <EvidenceQuote quote={q.quote} kind={q.kind} date={q.date} url={q.url} />
  );
}

// What is behind the node that was selected: the quote and source for a finding, the reasoning for
// an offering or a person, the pitch for the message, or why something was not found.
export function NodeDetail({ node }: { node: GraphNode | null }) {
  if (!node) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a box to see the quote, source and reasoning behind it.
      </p>
    );
  }
  const d = node.detail;
  switch (d.type) {
    case "company":
      return (
        <div>
          <h3 className="text-base font-bold">{d.name}</h3>
          {d.industry && (
            <p className="text-sm text-muted-foreground">{d.industry}</p>
          )}
          <p className="mt-2 text-sm">
            The lines to the right show what the company is doing, which of our
            offerings that points to, who to talk to, and what to say.
          </p>
        </div>
      );
    case "finding":
      return (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {d.kindLabel}
          </p>
          <h3 className="text-base font-bold">{d.statement}</h3>
          <QuoteLine q={d.quote} />
        </div>
      );
    case "offering":
      return (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {d.lead ? "Lead offering" : "Offering"} · {d.bandLabel}
          </p>
          <h3 className="text-base font-bold">{d.name}</h3>
          <p className="mt-1 text-sm">{d.reasoning}</p>
          {d.quotes.slice(0, 3).map((q) => (
            <QuoteLine key={`${q.url}-${q.quote}`} q={q} />
          ))}
        </div>
      );
    case "person":
      return (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {d.tierLabel}
            {d.startHere ? " · Start here" : ""}
          </p>
          <h3 className="text-base font-bold">{d.name}</h3>
          {d.title && (
            <p className="text-sm text-muted-foreground">{d.title}</p>
          )}
          {d.reasoning && <p className="mt-1 text-sm">{d.reasoning}</p>}
        </div>
      );
    case "message":
      return (
        <div>
          <h3 className="text-base font-bold">{d.pitch}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{d.why}</p>
          {d.points.length > 0 && (
            <ul className="mt-2 list-inside list-disc text-sm">
              {d.points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
        </div>
      );
    case "more":
      return (
        <div>
          <h3 className="text-base font-bold">{d.what}</h3>
          <ul className="mt-1 list-inside list-disc text-sm">
            {d.items.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </div>
      );
    case "gap":
      return (
        <div>
          <h3 className="text-base font-bold">{node.title}</h3>
          <p className="mt-1 text-sm">{d.text}</p>
        </div>
      );
  }
}
