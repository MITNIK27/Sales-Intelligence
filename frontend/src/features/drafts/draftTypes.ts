import type { DraftType } from "@/api/types";

// "follow_up" predates numbered follow-ups and is the first one.
export const DRAFT_TYPE_LABELS: Record<DraftType, string> = {
  first_touch: "First touch",
  follow_up: "Follow-up 1",
  follow_up_2: "Follow-up 2",
  follow_up_3: "Follow-up 3",
};

// The email that comes next, from how many have already been sent to this person. Only a starting
// point: the picker stays editable.
export function suggestedDraftType(sentCount: number): DraftType {
  if (sentCount <= 0) return "first_touch";
  if (sentCount === 1) return "follow_up";
  if (sentCount === 2) return "follow_up_2";
  return "follow_up_3";
}
