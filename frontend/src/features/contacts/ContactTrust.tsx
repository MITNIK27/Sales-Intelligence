import { StatusTag } from "@/components/StatusTag";

// A search-found person's standing, said the same way everywhere (the People tab and a company's
// window on the Market Discovery results): whether a person has confirmed them, and how sure the
// search was that they work at the company. The two are different facts, so both are shown, side by
// side, in the same words.
export function trustLine(
  confidence: number | null | undefined,
): string | null {
  if (confidence == null) return null;
  return `${Math.round(confidence * 100)}% sure they work here`;
}

export function trustDetail(confidence: number | null | undefined): string {
  const line = trustLine(confidence);
  if (line === null)
    return "Found by a web search. Check that they work here before reaching out.";
  const likely = confidence != null && confidence >= 0.8;
  return `Found by a web search, which is ${line.replace(" they work here", "")} they work here. ${
    likely
      ? "It looks like a match, but a person has not checked it."
      : "Check the company before reaching out."
  } Confirm the contact to start outreach.`;
}

export function ContactTrust({
  needsReview,
  confidence,
}: {
  needsReview: boolean;
  confidence: number | null | undefined;
}) {
  const line = trustLine(confidence);
  return (
    <>
      {needsReview ? (
        <span title={trustDetail(confidence)}>
          <StatusTag tone="watch" className="text-xs">
            Not confirmed yet
          </StatusTag>
        </span>
      ) : (
        <StatusTag tone="good" className="text-xs">
          Confirmed
        </StatusTag>
      )}
      {line && <span className="text-xs text-muted-foreground">{line}</span>}
    </>
  );
}
