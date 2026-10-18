import { describe, expect, it } from "vitest";

import type { DashboardRequirement } from "@/api/types";
import {
  attentionLabel,
  funnelHint,
  funnelWidth,
  requirementShares,
} from "@/features/dashboard/metrics";

const req = (
  meets: number,
  couldnt_verify: number,
  doesnt_meet: number,
): DashboardRequirement => ({
  name: "Operates in Europe",
  scope: "run",
  hard: true,
  meets,
  couldnt_verify,
  doesnt_meet,
  drafts_for_meeting: 0,
});

describe("funnelWidth", () => {
  it("is full for the first stage and proportional after", () => {
    expect(funnelWidth(10, 10)).toBe(100);
    expect(funnelWidth(1, 10)).toBe(10);
  });

  it("does not divide by zero on an empty funnel", () => {
    expect(funnelWidth(0, 0)).toBe(0);
  });

  it("stays within 0-100", () => {
    expect(funnelWidth(15, 10)).toBe(100);
    expect(funnelWidth(-3, 10)).toBe(0);
  });
});

describe("requirementShares", () => {
  it("adds to exactly 100 even when rounding would not", () => {
    const shares = requirementShares(req(1, 1, 1));
    expect(shares.meets + shares.unverified + shares.fails).toBe(100);
  });

  it("is all zero when nothing was judged", () => {
    expect(requirementShares(req(0, 0, 0))).toEqual({
      meets: 0,
      unverified: 0,
      fails: 0,
      total: 0,
    });
  });

  it("gives a requirement everyone meets a full green bar", () => {
    expect(requirementShares(req(5, 0, 0))).toMatchObject({
      meets: 100,
      unverified: 0,
      fails: 0,
    });
  });
});

describe("attentionLabel", () => {
  it("shortens known keys and falls back to the server label", () => {
    expect(
      attentionLabel("drafts_to_review", "Drafts waiting for your review"),
    ).toBe("Drafts to review");
    expect(attentionLabel("something_new", "Server wording")).toBe(
      "Server wording",
    );
  });
});

describe("funnelHint", () => {
  it("includes the percentage only when there is a previous step", () => {
    expect(funnelHint("Found", 10, null)).toBe("Found: 10");
    expect(funnelHint("Have a contact", 8, 89)).toBe(
      "Have a contact: 8 (89% of the step before)",
    );
  });
});
