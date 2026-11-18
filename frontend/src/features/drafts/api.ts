import { apiPost } from "@/api/client";
import type { Draft } from "@/api/types";

// Rewrite a draft the way the rep describes. `subject` and `body` are the text as it is on screen,
// hand edits included, because that is what gets rewritten.
export const refineDraft = (
  draftId: string,
  instruction: string,
  subject: string | null,
  body: string,
) =>
  apiPost<Draft>(`/drafts/${draftId}/refine`, { instruction, subject, body });

// Go back to the version before the last rewrite.
export const undoDraft = (draftId: string) =>
  apiPost<Draft>(`/drafts/${draftId}/undo`);
