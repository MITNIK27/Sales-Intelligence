import type { FitBand, OfferingFit, Product } from "@/api/types";

export type SuggestedOffering = { product: Product; band: FitBand };

const WORTH_SUGGESTING: FitBand[] = ["strong", "potential"];
export const EVERY_BAND: FitBand[] = [
  "strong",
  "potential",
  "weak",
  "insufficient_evidence",
];

// Our offerings that the research found a fit for at this company (by default only strong or
// possible ones; pass EVERY_BAND for everything that has been judged), best first. The same
// offering can be judged in several areas; its best judgement counts. Weak fits and offerings with
// too little evidence are not suggested.
export function suggestedOfferings(
  fits: OfferingFit[],
  products: Product[],
  max = 5,
  bands: FitBand[] = WORTH_SUGGESTING,
): SuggestedOffering[] {
  const best = new Map<string, OfferingFit>();
  for (const fit of fits) {
    if (!bands.includes(fit.band)) continue;
    const seen = best.get(fit.product_id);
    if (!seen || fit.score > seen.score) best.set(fit.product_id, fit);
  }
  return [...best.values()]
    .sort((a, b) => b.score - a.score)
    .flatMap((fit) => {
      const product = products.find((p) => p.id === fit.product_id);
      return product ? [{ product, band: fit.band }] : [];
    })
    .slice(0, max);
}
