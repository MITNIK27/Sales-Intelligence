import type { OfferingProposal, OfferingProposalChange, OfferingSyncStatus } from "@/api/types";
import { formatNumber, plural, timeAgo } from "@/lib/format";

export const CHANGE_LABEL: Record<OfferingProposalChange, string> = {
  new: "New",
  changed: "Changed",
  removed: "No longer on website",
};

// What the Approve button does for each kind of change, so the outcome is never a surprise.
export const APPROVE_LABEL: Record<OfferingProposalChange, string> = {
  new: "Add",
  changed: "Update",
  removed: "Archive",
};

// "Checking page 12 of 59…" while a check runs.
export function progressLabel(status: OfferingSyncStatus): string {
  const done = status.progress?.done;
  const total = status.progress?.total;
  if (typeof done === "number" && typeof total === "number" && total > 0) {
    return `Checking page ${formatNumber(done)} of ${formatNumber(total)}…`;
  }
  return "Starting the check…";
}

// "Checked 3 days ago · 2 new, 1 changed" / "Checked 3 days ago · nothing new".
export function lastCheckedLabel(status: OfferingSyncStatus, now?: number): string {
  if (!status.last_checked_at) return "Not checked yet";
  const result = status.last_result;
  const parts: string[] = [];
  if (result?.new) parts.push(`${formatNumber(result.new)} new`);
  if (result?.changed) parts.push(`${formatNumber(result.changed)} changed`);
  if (result?.removed) parts.push(`${formatNumber(result.removed)} removed`);
  const outcome = parts.length > 0 ? parts.join(", ") : "nothing new";
  return `Checked ${timeAgo(status.last_checked_at, now)} · ${outcome}`;
}

export function waitingLabel(count: number): string {
  return `${formatNumber(count)} ${plural(count, "change")} waiting for review`;
}

export function suggestionsLabel(count: number): string {
  return `Suggested from blog posts (${formatNumber(count)})`;
}

// The review list in three parts, so the screen opens on what matters: new and changed offerings
// first, then offerings that appear to have left the website, then blog-post suggestions.
export function groupProposals(proposals: OfferingProposal[]): {
  main: OfferingProposal[];
  removals: OfferingProposal[];
  suggestions: OfferingProposal[];
} {
  return {
    main: proposals.filter((p) => p.origin !== "post" && p.change !== "removed"),
    removals: proposals.filter((p) => p.change === "removed"),
    suggestions: proposals.filter((p) => p.origin === "post" && p.change !== "removed"),
  };
}

export function removalsLabel(count: number): string {
  return `No longer on the website (${formatNumber(count)})`;
}

// A readable message when the last check failed. Our own plain-language messages are shown as
// they are; anything technical is replaced by a short, neutral line.
export function failureLabel(error: string): string {
  return error.startsWith("Could not") && error.length <= 200
    ? error
    : "The last check failed. Try again.";
}
