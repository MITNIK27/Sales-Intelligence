import type { Product, ProductKind } from "@/api/types";

// The one place the user-facing words for products and services live. The API and database still
// say "product"; only what people read is "offering", so renaming again is a one-line change.
export const OFFERINGS_LABEL = "Our Offerings";
export const OFFERING_LABEL = "offering";
export const OFFERINGS_TAGLINE = "The services and products InfoBeans sells.";

export const KIND_ORDER: ProductKind[] = ["service", "product"];

export const KIND_LABEL: Record<ProductKind, string> = {
  service: "Service",
  product: "Product",
};

export const KIND_LABEL_PLURAL: Record<ProductKind, string> = {
  service: "Services",
  product: "Products",
};

export function kindOf(product: Product): ProductKind {
  return product.kind === "service" ? "service" : "product";
}

export function countByKind(products: Product[]): Record<ProductKind, number> {
  const counts: Record<ProductKind, number> = { service: 0, product: 0 };
  for (const product of products) counts[kindOf(product)] += 1;
  return counts;
}

// What the offerings picker button says, so a closed picker still shows what is chosen.
export function selectionSummary(products: Product[], selectedIds: Set<string>): string {
  const chosen = products.filter((product) => selectedIds.has(product.id));
  if (chosen.length === 0) return "Choose offerings";
  if (chosen.length === 1) return chosen[0].name;
  return `${chosen.length} offerings selected`;
}

// Services first, then products, each alphabetical, for pickers that show both at once.
export function groupByKind(products: Product[]): { kind: ProductKind; items: Product[] }[] {
  return KIND_ORDER.map((kind) => ({
    kind,
    items: products
      .filter((product) => kindOf(product) === kind)
      .sort((a, b) => a.name.localeCompare(b.name)),
  })).filter((group) => group.items.length > 0);
}
