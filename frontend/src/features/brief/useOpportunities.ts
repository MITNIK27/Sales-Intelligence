import { useCallback, useEffect, useRef, useState } from "react";

import type { CompanyOpportunity } from "@/api/types";
import {
  createOpportunity,
  fetchJob,
  fetchOpportunities,
  researchOffers,
  startAssessment,
  suggestAreas,
  waitForJob,
} from "@/features/brief/api";

const POLL_INTERVAL_MS = 1500;

// A company's opportunities, with a way to look into one. Looking into an area runs in the
// background, so each one being researched is tracked by id and the list is reloaded when the job
// finishes; the rest of the list stays on screen the whole time.
export function useOpportunities(companyId: string | null) {
  const [items, setItems] = useState<CompanyOpportunity[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [researching, setResearching] = useState<Set<string>>(new Set());
  const [suggesting, setSuggesting] = useState(false);
  const [findingOffers, setFindingOffers] = useState(false);
  const timers = useRef<Set<number>>(new Set());

  const reload = useCallback(async () => {
    if (!companyId) return;
    try {
      setItems(await fetchOpportunities(companyId));
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "could not load the opportunities",
      );
    }
  }, [companyId]);

  useEffect(() => {
    setItems(null);
    reload();
    const active = timers.current;
    return () => {
      active.forEach((timer) => window.clearInterval(timer));
      active.clear();
    };
  }, [reload]);

  function finish(opportunityId: string) {
    setResearching((current) => {
      const next = new Set(current);
      next.delete(opportunityId);
      return next;
    });
  }

  async function research(opportunityId: string, force = false) {
    setError(null);
    setResearching((current) => new Set(current).add(opportunityId));
    try {
      const { job_id } = await startAssessment(opportunityId, force);
      const timer = window.setInterval(async () => {
        try {
          const job = await fetchJob(job_id);
          if (job.status !== "done" && job.status !== "failed") return;
          window.clearInterval(timer);
          timers.current.delete(timer);
          if (job.status === "failed")
            setError(job.error ?? "the research did not finish");
          await reload();
          finish(opportunityId);
        } catch {
          // One failed poll must not end the loop; the next tick retries.
        }
      }, POLL_INTERVAL_MS);
      timers.current.add(timer);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "could not start the research",
      );
      finish(opportunityId);
    }
  }

  // Start looking into an area the person typed; returns it so the screen can select it.
  async function addArea(label: string): Promise<CompanyOpportunity | null> {
    if (!companyId) return null;
    setError(null);
    try {
      const created = await createOpportunity(companyId, label);
      await reload();
      research(created.id);
      return created;
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not add that area");
      return null;
    }
  }

  // Start the overall view (no specific area), which is where "which offerings fit" lives.
  async function startOverall() {
    if (!companyId) return;
    try {
      await createOpportunity(companyId, null);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start");
    }
  }

  // Ask for other areas the evidence points to; they arrive as suggested areas.
  async function suggest(refresh = false) {
    if (!companyId || suggesting) return;
    setSuggesting(true);
    setError(null);
    try {
      const { job_id } = await suggestAreas(companyId, refresh);
      const job = await waitForJob(job_id, () => false);
      if (job?.status === "failed")
        setError(job.error ?? "could not look for other areas");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start");
    } finally {
      setSuggesting(false);
    }
  }

  // Research what we could offer the company as a whole. Returns the id of the company's overall
  // opportunity (where the result is kept), or null when it did not finish.
  async function findOffers(): Promise<string | null> {
    if (!companyId) return null;
    setFindingOffers(true);
    setError(null);
    try {
      const { job_id } = await researchOffers(companyId);
      const job = await waitForJob(job_id, () => false);
      if (job?.status === "failed") {
        setError(job.error ?? "could not research what we could offer");
        return null;
      }
      await reload();
      const result = job?.result as { opportunity_id?: string } | null;
      return result?.opportunity_id ?? null;
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start");
      return null;
    } finally {
      setFindingOffers(false);
    }
  }

  return {
    items,
    error,
    researching,
    suggesting,
    findingOffers,
    findOffers,
    research,
    reload,
    addArea,
    startOverall,
    suggest,
  };
}
