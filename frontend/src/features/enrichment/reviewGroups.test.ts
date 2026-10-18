import { describe, expect, it } from "vitest";

import type { NeedsReviewItem } from "@/api/types";
import {
  companyKey,
  contactKey,
  groupByCompany,
  groupKeys,
  pruneSelection,
  selectionState,
  splitSelection,
  toggleKeys,
} from "@/features/enrichment/reviewGroups";

const person = (
  company: string,
  id: string,
  name: string,
  at: string,
): NeedsReviewItem => ({
  entity_type: "contact",
  company_id: company,
  company_name: `Company ${company}`,
  contact_id: id,
  contact_name: name,
  reason: "found via contact search, not confirmed",
  flagged_at: at,
});

const flaggedCompany = (company: string, at: string): NeedsReviewItem => ({
  entity_type: "company",
  company_id: company,
  company_name: `Company ${company}`,
  contact_id: null,
  contact_name: null,
  reason: "domain found via search API, not confirmed",
  flagged_at: at,
});

describe("groupByCompany", () => {
  it("puts each company's people together, newest company first", () => {
    const groups = groupByCompany([
      person("a", "1", "Zoe", "2026-10-01T00:00:00Z"),
      person("b", "2", "Max", "2026-10-03T00:00:00Z"),
      person("a", "3", "Amy", "2026-10-02T00:00:00Z"),
    ]);
    expect(groups.map((g) => g.companyId)).toEqual(["b", "a"]);
    expect(groups[1].contacts.map((c) => c.contact_name)).toEqual([
      "Amy",
      "Zoe",
    ]);
  });

  it("keeps a flagged company on its group instead of listing it as a person", () => {
    const [group] = groupByCompany([
      flaggedCompany("a", "2026-10-01T00:00:00Z"),
      person("a", "1", "Amy", "2026-10-01T00:00:00Z"),
    ]);
    expect(group.companyFlag).not.toBeNull();
    expect(group.contacts).toHaveLength(1);
    expect(groupKeys(group).sort()).toEqual(
      [companyKey("a"), contactKey("1")].sort(),
    );
  });
});

describe("selection", () => {
  const keys = [contactKey("1"), contactKey("2")];

  it("reports none, some and all", () => {
    expect(selectionState(new Set(), keys)).toBe("none");
    expect(selectionState(new Set([contactKey("1")]), keys)).toBe("some");
    expect(selectionState(new Set(keys), keys)).toBe("all");
    expect(selectionState(new Set(keys), [])).toBe("none");
  });

  it("toggles a whole group on, and off again when it was already fully selected", () => {
    const on = toggleKeys(new Set([contactKey("9")]), keys);
    expect(selectionState(on, keys)).toBe("all");
    expect(on.has(contactKey("9"))).toBe(true); // other groups are untouched
    const off = toggleKeys(on, keys);
    expect(selectionState(off, keys)).toBe("none");
    expect(off.has(contactKey("9"))).toBe(true);
  });

  it("completes a partial selection rather than clearing it", () => {
    const next = toggleKeys(new Set([contactKey("1")]), keys);
    expect(selectionState(next, keys)).toBe("all");
  });

  it("splits the selection into company and contact ids", () => {
    expect(
      splitSelection(
        new Set([companyKey("a"), contactKey("1"), contactKey("2")]),
      ),
    ).toEqual({
      companyIds: ["a"],
      contactIds: ["1", "2"],
    });
  });

  it("forgets selections for rows that no longer exist", () => {
    const groups = groupByCompany([
      person("a", "1", "Amy", "2026-10-01T00:00:00Z"),
    ]);
    const kept = pruneSelection(
      new Set([contactKey("1"), contactKey("gone")]),
      groups,
    );
    expect(Array.from(kept)).toEqual([contactKey("1")]);
  });
});
