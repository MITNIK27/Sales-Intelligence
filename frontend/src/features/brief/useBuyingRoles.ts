import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { ContactRelevance } from "@/api/types";
import {
  fetchContacts,
  fetchFit,
  fetchOpportunities,
} from "@/features/brief/api";
import { pickOpportunity } from "@/features/brief/opportunityLabels";
import { focusOffering } from "@/features/brief/useBriefDetail";
import { useBriefFilter } from "@/features/brief/useBriefFilter";
import { useOfferingOptions } from "@/features/brief/useOfferingOptions";

// Each person's part in the buying decision, for the same opportunity and offering the Brief tab is
// showing, so a role set there shows here too. Read again when `refreshKey` changes (the Brief
// changed something). Empty until something is judged.
export function useBuyingRoles(
  companyId: string,
  active: boolean,
  runOfferingIds: string[],
  refreshKey = 0,
): Record<string, ContactRelevance> {
  const [params] = useSearchParams();
  const offerings = useOfferingOptions();
  const filter = useBriefFilter(runOfferingIds, offerings.known);
  const [roles, setRoles] = useState<Record<string, ContactRelevance>>({});
  const area = params.get("area");
  const chosen = filter.offeringIds.join(",");

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    (async () => {
      try {
        const opportunity = pickOpportunity(
          await fetchOpportunities(companyId),
          area,
        );
        if (!opportunity) return;
        const focus = focusOffering(
          await fetchFit(opportunity.id),
          chosen ? chosen.split(",") : [],
        );
        if (!focus) return;
        const rows = await fetchContacts(opportunity.id, focus.product_id);
        if (!cancelled)
          setRoles(Object.fromEntries(rows.map((r) => [r.contact_id, r])));
      } catch {
        // Supplementary: the people list works without it.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [companyId, active, area, chosen, refreshKey]);

  return roles;
}
