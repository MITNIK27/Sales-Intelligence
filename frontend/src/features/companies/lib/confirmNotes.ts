import type { CompanyConfirmResult } from "@/api/types";

// What Confirm Company did and did not do, from the two steps it runs after confirming. The
// backend gives a reason for every step it skipped; this turns the reasons into plain sentences so
// "no drafts appeared" is never left unexplained.
const REASON: Record<string, string> = {
  "no product specified":
    "No offering was chosen, so no drafts were written. Choose an offering and draft from a person's card.",
  "no primary-target contacts identified":
    "No contact matched a target role, so no drafts were written. Check the People tab.",
  "no contacts to classify":
    "There are no contacts yet, so roles were not worked out. Find people or add someone.",
  "role classification did not run":
    "Roles were not worked out, so drafting was skipped.",
};

function reasonOf(step: Record<string, unknown> | undefined): string | null {
  const raw = step?.skipped_reason;
  if (typeof raw !== "string" || !raw) return null;
  return REASON[raw] ?? raw.charAt(0).toUpperCase() + raw.slice(1) + ".";
}

export function confirmNotes(result: CompanyConfirmResult): string[] {
  const notes = [
    reasonOf(result.role_classification),
    reasonOf(result.drafting),
  ].filter((n): n is string => n !== null);
  return [...new Set(notes)];
}
