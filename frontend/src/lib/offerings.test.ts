import { describe, expect, it } from "vitest";

import type { Product } from "@/api/types";
import { countByKind, groupByKind, kindOf, selectionSummary } from "@/lib/offerings";

function offering(name: string, kind: Product["kind"]): Product {
  return {
    id: name,
    name,
    description: null,
    kind,
    source: "manual",
    source_url: null,
    status: "active",
    created_at: "2026-10-28T00:00:00Z",
    updated_at: "2026-10-28T00:00:00Z",
  };
}

describe("offerings", () => {
  it("treats anything that is not a service as a product", () => {
    expect(kindOf(offering("Cloud", "service"))).toBe("service");
    expect(kindOf(offering("Spacewarp", "product"))).toBe("product");
  });

  it("counts each kind", () => {
    const list = [offering("A", "service"), offering("B", "product"), offering("C", "service")];
    expect(countByKind(list)).toEqual({ service: 2, product: 1 });
  });

  it("summarises the chosen offerings for the picker button", () => {
    const list = [offering("Cloud", "service"), offering("Spacewarp", "product")];
    expect(selectionSummary(list, new Set())).toBe("Choose offerings");
    expect(selectionSummary(list, new Set(["Cloud"]))).toBe("Cloud");
    expect(selectionSummary(list, new Set(["Cloud", "Spacewarp"]))).toBe("2 offerings selected");
  });

  it("groups services before products, alphabetically, and drops empty groups", () => {
    const list = [offering("Zeta", "product"), offering("Beta", "service"), offering("Alpha", "service")];
    const groups = groupByKind(list);
    expect(groups.map((g) => g.kind)).toEqual(["service", "product"]);
    expect(groups[0].items.map((p) => p.name)).toEqual(["Alpha", "Beta"]);
    expect(groupByKind([offering("Only", "product")]).map((g) => g.kind)).toEqual(["product"]);
  });
});
