import { useCallback, useEffect, useState } from "react";

import { apiGet } from "@/api/client";
import type { OutreachActivity } from "@/api/types";

// What has been logged for one person, newest first. It is only fetched once `enabled`, so a page of
// people does not ask for every history up front; after that `reload` refreshes it (after a log, or
// a change on the follow-up tab). Supplementary: a failure leaves the last list in place.
export function useOutreachHistory(contactId: string, enabled: boolean) {
  const [history, setHistory] = useState<OutreachActivity[] | null>(null);

  const reload = useCallback(
    () =>
      apiGet<OutreachActivity[]>(`/contacts/${contactId}/outreach-activities`)
        .then(setHistory)
        .catch(() => {
          // Logging and following up still work without the list.
        }),
    [contactId],
  );

  useEffect(() => {
    setHistory(null);
  }, [contactId]);

  useEffect(() => {
    if (enabled) void reload();
  }, [enabled, reload]);

  return { history, reload };
}
