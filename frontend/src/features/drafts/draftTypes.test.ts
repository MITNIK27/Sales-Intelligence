import { describe, expect, it } from "vitest";

import {
  DRAFT_TYPE_LABELS,
  suggestedDraftType,
} from "@/features/drafts/draftTypes";

describe("draft types", () => {
  it("suggests the next email in the sequence from how many were sent", () => {
    expect(suggestedDraftType(0)).toBe("first_touch");
    expect(suggestedDraftType(1)).toBe("follow_up");
    expect(suggestedDraftType(2)).toBe("follow_up_2");
    expect(suggestedDraftType(3)).toBe("follow_up_3");
    expect(suggestedDraftType(9)).toBe("follow_up_3");
  });

  it("keeps the original follow-up as Follow-up 1", () => {
    expect(DRAFT_TYPE_LABELS.follow_up).toBe("Follow-up 1");
  });
});
