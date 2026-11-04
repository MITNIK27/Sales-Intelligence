import type { Product } from "@/api/types";

// An offering the person picked, and the area a brief around it would research. The area is the
// offering's first area tag (what it is sold into), or its own name when it has none.
export type BriefTarget = { id: string; name: string; areaLabel: string };

export function briefTargets(
  chosenIds: string[],
  products: Product[] | null,
): BriefTarget[] {
  const byId = new Map((products ?? []).map((p) => [p.id, p]));
  const targets: BriefTarget[] = [];
  for (const id of chosenIds) {
    const product = byId.get(id);
    if (!product) continue;
    const tag = product.buyer_profile?.area_tags?.find((t) => t.trim());
    targets.push({
      id,
      name: product.name,
      areaLabel: (tag ?? product.name).trim(),
    });
  }
  return targets;
}

// An area name as it is shown: each word starts with a capital ("application modernization" becomes
// "Application Modernization"). A word that already has a capital in it (SAP, DevOps) is left alone.
export function titleCaseArea(label: string): string {
  return label
    .trim()
    .split(/\s+/)
    .map((w) =>
      w === w.toLowerCase() ? w.charAt(0).toUpperCase() + w.slice(1) : w,
    )
    .join(" ");
}

// The chosen offerings that already have a researched brief of their own: an area named for the
// offering exists and has been looked into. Those are finished, so they are not offered again.
export function doneOfferingIds(
  areas: { area_label: string; assessment: unknown | null }[],
  products: Product[] | null,
): Set<string> {
  const researched = new Set(
    areas
      .filter((a) => a.assessment !== null)
      .map((a) => a.area_label.trim().toLowerCase()),
  );
  const done = new Set<string>();
  for (const t of briefTargets(
    (products ?? []).map((p) => p.id),
    products,
  )) {
    if (researched.has(t.areaLabel.toLowerCase())) done.add(t.id);
  }
  return done;
}
