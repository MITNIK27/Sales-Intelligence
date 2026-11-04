import { useEffect, useRef, useState } from "react";

import type { JobStatus } from "@/api/types";
import { fetchJob, startScrape } from "@/features/companies/api";
import { errorMessage } from "@/features/companies/lib/contacts";

const POLL_INTERVAL_MS = 1500;
const WATCH_INTERVAL_MS = 2000;

// Starts a re-scrape of the company and follows its job until it finishes, reloading the company
// and its signals at the end. Polling stops when the page is left or another company is opened.
export function useEnrichmentJob(
  companyId: string | undefined,
  // The company's current enrichment status; while it is "pending" the page watches for it to finish.
  status: string | undefined,
  actions: {
    reloadCompany: () => Promise<void> | undefined;
    refreshCompany: () => Promise<void>;
    reloadSignals: () => Promise<void> | undefined;
    onError: (message: string) => void;
  },
) {
  const [scrapeJob, setScrapeJob] = useState<JobStatus | null>(null);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    },
    [companyId],
  );

  // A company can arrive already "pending" (for example after "Go deeper" in Quick Check started
  // its scrape), so no click happened on this page. Watch it until it is no longer pending, then
  // load what the scrape found.
  const wasPending = useRef(false);
  const { refreshCompany, reloadSignals } = actions;
  useEffect(() => {
    if (status === "pending") {
      wasPending.current = true;
      const timer = window.setInterval(() => {
        void refreshCompany();
      }, WATCH_INTERVAL_MS);
      return () => window.clearInterval(timer);
    }
    if (wasPending.current) {
      wasPending.current = false;
      void reloadSignals();
    }
    return undefined;
    // The actions are recreated on every render; only the status and company decide this.
  }, [status, companyId]);

  async function start() {
    if (!companyId) return;
    setTriggering(true);
    setScrapeJob(null);
    try {
      const started = await startScrape(companyId);
      await actions.reloadCompany(); // reflects enrichment_status -> "pending" immediately
      pollRef.current = window.setInterval(async () => {
        const status = await fetchJob(started.job_id);
        setScrapeJob(status);
        if (status.status === "done" || status.status === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          await actions.reloadCompany();
          await actions.reloadSignals();
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      actions.onError(errorMessage(err, "failed to start scrape"));
    } finally {
      setTriggering(false);
    }
  }

  return { scrapeJob, triggering, start };
}
