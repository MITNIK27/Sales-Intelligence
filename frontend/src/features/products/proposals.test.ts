import { describe, expect, it } from "vitest";

import type { OfferingProposal, OfferingSyncStatus } from "@/api/types";
import {
  failureLabel,
  lastCheckedLabel,
  progressLabel,
  groupProposals,
  removalsLabel,
  suggestionsLabel,
  waitingLabel,
} from "@/features/products/proposals";

const base: OfferingSyncStatus = {
  running: false,
  job_id: null,
  progress: null,
  last_checked_at: null,
  last_result: null,
  last_error: null,
  pending_count: 0,
};

describe("offering sync labels", () => {
  it("shows progress while a check runs, and a neutral start before it reports", () => {
    expect(progressLabel({ ...base, running: true, progress: { done: 12, total: 59 } })).toBe(
      "Checking page 12 of 59…",
    );
    expect(progressLabel({ ...base, running: true })).toBe("Starting the check…");
  });

  it("says when the site was last checked and what it found", () => {
    const now = new Date("2026-10-28T12:00:00Z").getTime();
    const checked = "2026-10-25T12:00:00Z";
    expect(lastCheckedLabel(base, now)).toBe("Not checked yet");
    expect(
      lastCheckedLabel({ ...base, last_checked_at: checked, last_result: { new: 2, changed: 1 } }, now),
    ).toBe("Checked 3 days ago · 2 new, 1 changed");
    expect(lastCheckedLabel({ ...base, last_checked_at: checked, last_result: {} }, now)).toBe(
      "Checked 3 days ago · nothing new",
    );
  });

  it("counts waiting changes", () => {
    expect(waitingLabel(1)).toBe("1 change waiting for review");
    expect(waitingLabel(5)).toBe("5 changes waiting for review");
  });

  it("splits the review list into new/changed, removals and blog-post suggestions", () => {
    const make = (
      id: string,
      origin: OfferingProposal["origin"],
      change: OfferingProposal["change"] = "new",
    ) => ({ id, origin, change }) as OfferingProposal;
    const { main, removals, suggestions } = groupProposals([
      make("a", "site"),
      make("b", "post"),
      make("c", "menu"),
      make("d", "site", "removed"),
    ]);
    expect(main.map((p) => p.id)).toEqual(["a", "c"]);
    expect(removals.map((p) => p.id)).toEqual(["d"]);
    expect(suggestions.map((p) => p.id)).toEqual(["b"]);
    expect(suggestionsLabel(3)).toBe("Suggested from blog posts (3)");
    expect(removalsLabel(36)).toBe("No longer on the website (36)");
  });

  it("shows our own failure messages and hides technical ones", () => {
    expect(failureLabel("Could not read 6 of 6 pages. Nothing was changed.")).toBe(
      "Could not read 6 of 6 pages. Nothing was changed.",
    );
    expect(failureLabel("(sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) ...")).toBe(
      "The last check failed. Try again.",
    );
  });
});
