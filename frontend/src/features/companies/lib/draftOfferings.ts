import type { FitBand, OfferingFit, Product } from "@/api/types";

// Why an offering is offered for a draft. The order here is the order the groups are listed in:
// what the rep searched for, then what they made a brief around, then what the Brief found a fit for.
export type DraftSource = "search" | "brief" | "fit";

export const DRAFT_SOURCE_HEADING: Record<DraftSource, string> = {
  search: "Searched in Market Discovery",
  brief: "Briefs you made",
  fit: "Fit for this company",
};

export type DraftOffering = {
  product: Product;
  // How well it fits this company, when the research judged it; null when nobody has looked.
  band: FitBand | null;
  // Its best fit score, only used to find the recommended one.
  score: number;
  source: DraftSource;
};

const WORTH_PITCHING: FitBand[] = ["strong", "potential"];

// The offerings a draft can be written about. Anything the rep chose themselves (searched for in
// Market Discovery, or made a brief around) is listed whatever its fit says, because they asked for
// it; the rest of the catalogue is listed only when the Brief found a strong or possible fit. An
// offering appears once, under the first reason that applies.
export function draftOfferings({
  fits,
  products,
  searchedIds,
  briefedIds,
}: {
  fits: OfferingFit[];
  products: Product[];
  searchedIds: Iterable<string>;
  briefedIds: Iterable<string>;
}): DraftOffering[] {
  const byId = new Map(products.map((p) => [p.id, p]));
  const best = new Map<string, OfferingFit>();
  for (const fit of fits) {
    const seen = best.get(fit.product_id);
    if (!seen || fit.score > seen.score) best.set(fit.product_id, fit);
  }
  const out: DraftOffering[] = [];
  const used = new Set<string>();
  const add = (id: string, source: DraftSource) => {
    const product = byId.get(id);
    if (!product || used.has(id)) return;
    used.add(id);
    const fit = best.get(id);
    out.push({
      product,
      band: fit?.band ?? null,
      score: fit?.score ?? 0,
      source,
    });
  };
  for (const id of searchedIds) add(id, "search");
  for (const id of briefedIds) add(id, "brief");
  [...best.values()]
    .filter((f) => WORTH_PITCHING.includes(f.band))
    .sort((a, b) => b.score - a.score)
    .forEach((f) => add(f.product_id, "fit"));
  return out;
}

// The one to start on: the best strong or possible fit among the options, if there is one;
// otherwise the first thing listed.
export function recommendedOffering(options: DraftOffering[]): string {
  const fits = options.filter(
    (o) => o.band !== null && WORTH_PITCHING.includes(o.band),
  );
  const top = fits.reduce<DraftOffering | null>(
    (a, b) => (a === null || b.score > a.score ? b : a),
    null,
  );
  return (top ?? options[0])?.product.id ?? "";
}

// Whether the start choice was made on fit (so it can be called "the best fit").
export function isBestFit(options: DraftOffering[], id: string): boolean {
  const o = options.find((x) => x.product.id === id);
  return !!o && o.band !== null && WORTH_PITCHING.includes(o.band);
}
