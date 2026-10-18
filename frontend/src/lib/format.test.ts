import { describe, expect, it } from "vitest";

import { plural, timeAgo } from "@/lib/format";

const NOW = new Date("2026-10-05T12:00:00Z").getTime();
const ago = (ms: number) => new Date(NOW - ms).toISOString();

describe("timeAgo", () => {
  it("says just now under a minute", () => {
    expect(timeAgo(ago(20_000), NOW)).toBe("just now");
  });

  it("uses minutes, hours and days", () => {
    expect(timeAgo(ago(5 * 60_000), NOW)).toBe("5 min ago");
    expect(timeAgo(ago(19 * 3_600_000), NOW)).toBe("19 h ago");
    expect(timeAgo(ago(24 * 3_600_000), NOW)).toBe("1 day ago");
    expect(timeAgo(ago(72 * 3_600_000), NOW)).toBe("3 days ago");
  });

  it("never goes negative for a timestamp slightly in the future", () => {
    expect(timeAgo(ago(-5_000), NOW)).toBe("just now");
  });
});

describe("plural", () => {
  it("picks the singular only for exactly one", () => {
    expect(plural(1, "company", "companies")).toBe("company");
    expect(plural(0, "company", "companies")).toBe("companies");
    expect(plural(2, "draft")).toBe("drafts");
  });
});
