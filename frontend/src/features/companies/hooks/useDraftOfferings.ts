import { useEffect, useMemo, useState } from "react";

import type { CompanyOpportunity, OfferingFit, Product } from "@/api/types";
import {
  fetchFit,
  fetchOpportunities,
  fetchSearchContext,
} from "@/features/brief/api";
import { doneOfferingIds } from "@/features/brief/startBrief";
import {
  draftOfferings,
  type DraftOffering,
} from "@/features/companies/lib/draftOfferings";

// The offerings a draft for this company can be written about: what the rep searched for in Market
// Discovery, what they made a brief around, and what the Brief found a fit for. Supplementary: if
// any part cannot be loaded, the list is built from the rest.
export function useDraftOfferings(
  companyId: string,
  products: Product[],
): DraftOffering[] {
  const [opps, setOpps] = useState<CompanyOpportunity[]>([]);
  const [fits, setFits] = useState<OfferingFit[]>([]);
  const [searchedIds, setSearchedIds] = useState<string[]>([]);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const items = await fetchOpportunities(companyId);
        const rows = await Promise.all(
          items
            .filter((o) => o.assessment !== null)
            .map((o) => fetchFit(o.id).catch(() => [])),
        );
        if (live) {
          setOpps(items);
          setFits(rows.flat());
        }
      } catch {
        // Supplementary.
      }
      try {
        const context = await fetchSearchContext(companyId);
        const ids = context.runs.flatMap((r) =>
          r.offerings.map((o) => o.product_id),
        );
        if (live) setSearchedIds([...new Set(ids)]);
      } catch {
        // Supplementary.
      }
    })();
    return () => {
      live = false;
    };
  }, [companyId]);

  return useMemo(
    () =>
      draftOfferings({
        fits,
        products,
        searchedIds,
        briefedIds: doneOfferingIds(opps, products),
      }),
    [fits, products, searchedIds, opps],
  );
}
