import { useEffect, useState } from "react";

import { fetchRunOfferings, type RunOffering } from "@/features/brief/api";

// The offerings chosen for the Market Discovery run a company was opened from (none when it was
// opened any other way). A failed lookup just means no pre-selection; nothing else depends on it.
export function useRunOfferings(runId: string | null): RunOffering[] {
  const [offerings, setOfferings] = useState<RunOffering[]>([]);
  useEffect(() => {
    let cancelled = false;
    setOfferings([]);
    if (runId)
      fetchRunOfferings(runId)
        .then((rows) => !cancelled && setOfferings(rows))
        .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [runId]);
  return offerings;
}
