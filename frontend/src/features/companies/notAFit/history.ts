import type { CompanyDismissResult } from "@/api/types";

type Counts = { outreach_activities: number; sent_drafts: number };

const plural = (n: number, one: string, many: string) =>
  `${n} ${n === 1 ? one : many}`;

// What would be hidden, in words: "2 logged outreach activities and 1 sent draft".
export function describeHistory({ outreach_activities, sent_drafts }: Counts) {
  const parts: string[] = [];
  if (outreach_activities > 0)
    parts.push(
      `${plural(outreach_activities, "logged outreach activity", "logged outreach activities")}`,
    );
  if (sent_drafts > 0) parts.push(plural(sent_drafts, "sent draft", "sent drafts"));
  return parts.join(" and ");
}

// The toast after marking companies not a fit.
export function dismissalSummary(result: CompanyDismissResult): string {
  const parts: string[] = [];
  if (result.dismissed > 0)
    parts.push(`${plural(result.dismissed, "company", "companies")} marked not a fit`);
  if (result.already_dismissed > 0)
    parts.push(`${result.already_dismissed} already ${result.already_dismissed === 1 ? "was" : "were"}`);
  if (result.not_found.length > 0)
    parts.push(`${result.not_found.length} could not be found`);
  if (parts.length === 0) return "Nothing changed.";
  const text = parts.join(", ");
  return `${text[0].toUpperCase()}${text.slice(1)}.`;
}
