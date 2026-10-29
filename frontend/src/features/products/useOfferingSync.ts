import { useCallback, useEffect, useRef, useState } from "react";

import { apiGet, apiPost } from "@/api/client";
import type { OfferingSyncStatus } from "@/api/types";

const POLL_MS = 2000;

// The "Check for updates" state: loads the status, starts a check, and polls only while one is
// running. `onFinished` fires once when a running check ends, so the page can reload its lists.
export function useOfferingSync(onFinished: () => void) {
  const [status, setStatus] = useState<OfferingSyncStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wasRunning = useRef(false);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  const refresh = useCallback(async () => {
    try {
      const next = await apiGet<OfferingSyncStatus>("/products/sync/status");
      setStatus(next);
      setError(null);
      if (wasRunning.current && !next.running) finished.current();
      wasRunning.current = next.running;
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load the check status");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const running = status?.running ?? false;
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, refresh]);

  const start = useCallback(async () => {
    setError(null);
    try {
      await apiPost("/products/sync");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start the check");
    }
  }, [refresh]);

  return { status, error, start, refresh };
}
