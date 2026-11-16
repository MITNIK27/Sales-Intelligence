import { useCallback, useEffect, useState } from "react";

import type { SearchContext } from "@/api/types";
import { fetchSearchContext } from "@/features/brief/api";

const POLL_MS = 4000;

// What the company was searched for in Market Discovery, read from the company itself (not the
// address), so it is there however the company was opened. While an offering is still being worked
// out the answer is fetched again every few seconds (only when `poll` is set, so a second reader of
// the same data does not double the requests).
export function useSearchContext(companyId: string | null, poll = false) {
  const [context, setContext] = useState<SearchContext | null>(null);

  const reload = useCallback(async () => {
    if (!companyId) return;
    try {
      setContext(await fetchSearchContext(companyId));
    } catch {
      // The card is extra information; the Brief works without it.
    }
  }, [companyId]);

  useEffect(() => {
    setContext(null);
    void reload();
  }, [reload]);

  const working = !!context?.runs.some((r) =>
    r.offerings.some((o) => o.state === "working"),
  );
  useEffect(() => {
    if (!poll || !working) return;
    const timer = window.setInterval(() => void reload(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [poll, working, reload]);

  return { context, reload };
}
