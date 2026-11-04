import { useEffect, useState } from "react";

import type { OfferingFit } from "@/api/types";
import { fetchFit, fetchOpportunities } from "@/features/brief/api";

// Every offering judgement made for this company across its researched areas. Supplementary: if
// it cannot be loaded the list is simply empty and the offering picker works as before.
export function useCompanyFits(companyId: string): OfferingFit[] {
  const [fits, setFits] = useState<OfferingFit[]>([]);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const opps = await fetchOpportunities(companyId);
        const rows = await Promise.all(
          opps
            .filter((o) => o.assessment !== null)
            .map((o) => fetchFit(o.id).catch(() => [])),
        );
        if (live) setFits(rows.flat());
      } catch {
        // Supplementary.
      }
    })();
    return () => {
      live = false;
    };
  }, [companyId]);
  return fits;
}
