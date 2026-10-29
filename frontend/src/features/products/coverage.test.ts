import { describe, expect, it } from "vitest";

import type { OfferingCoveragePage, OfferingMenuItem } from "@/api/types";
import {
  canTreatAsOffering,
  filterPages,
  menuSummary,
  needsAttention,
  pageSlice,
  sortMenu,
  splitScreened,
} from "@/features/products/coverage";

function page(url: string, verdict: OfferingCoveragePage["verdict"], title: string | null = null) {
  return {
    url,
    title,
    lane: "site",
    verdict,
    reason: null,
    lastmod: null,
    last_checked_at: null,
    force_extract: false,
  } as OfferingCoveragePage;
}

function item(label: string, status: OfferingMenuItem["status"]): OfferingMenuItem {
  return { group: "Innovation", label, url: `https://x/${label}/`, status };
}

describe("coverage helpers", () => {
  it("counts menu entries that need a look and puts the gaps first", () => {
    const menu = [item("Stanza", "covered"), item("Expona", "missing"), item("BFSI", "judged_not_offering")];
    expect(menuSummary(menu)).toEqual({ total: 3, attention: 2 });
    expect(needsAttention(menu[0])).toBe(false);
    expect(sortMenu(menu).map((m) => m.label)).toEqual(["Expona", "BFSI", "Stanza"]);
  });

  it("filters pages by verdict and by text in the address or title", () => {
    const pages = [
      page("https://infobeans.ai/cloud/", "offering", "Cloud"),
      page("https://infobeans.ai/bfsi/", "not_offering"),
      page("https://infobeans.ai/gcc/", "failed"),
    ];
    expect(filterPages(pages, "", "all")).toHaveLength(3);
    expect(filterPages(pages, "", "not_offering").map((p) => p.url)).toEqual([
      "https://infobeans.ai/bfsi/",
    ]);
    expect(filterPages(pages, "CLOUD", "all")).toHaveLength(1);
  });

  it("only offers 'treat as offering' where it makes sense", () => {
    expect(canTreatAsOffering(page("u", "offering"))).toBe(false);
    expect(canTreatAsOffering(page("u", "not_offering"))).toBe(true);
    expect(canTreatAsOffering({ ...page("u", "failed"), force_extract: true })).toBe(false);
  });

  it("keeps screened-out blog posts apart from the pages that matter", () => {
    const post = { ...page("https://x/post", "not_offering"), lane: "post" } as OfferingCoveragePage;
    const site = page("https://x/bfsi", "not_offering");
    const { main, screened } = splitScreened([post, site]);
    expect(main).toEqual([site]);
    expect(screened).toEqual([post]);
  });

  it("slices a list into pages and keeps the page number in range", () => {
    const items = [1, 2, 3, 4, 5];
    expect(pageSlice(items, 2, 2)).toEqual({ rows: [3, 4], page: 2 });
    expect(pageSlice(items, 99, 2)).toEqual({ rows: [5], page: 3 });
    expect(pageSlice([], 1, 25)).toEqual({ rows: [], page: 1 });
  });
});
