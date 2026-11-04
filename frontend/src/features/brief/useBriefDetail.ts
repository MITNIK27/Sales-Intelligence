import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  BuyingRole,
  ContactRelevance,
  OfferingFit,
  Recommendation,
} from "@/api/types";
import {
  clearRelevance,
  fetchContacts,
  fetchFit,
  fetchOpportunityRecommendations,
  setRelevance,
  startAnalysis,
  startRecommendation,
  waitForJob,
} from "@/features/brief/api";

// The job's own explanation when it finished with nothing to show (see `outcome` in the backend).
const jobOutcome = (result: unknown): string | null => {
  const outcome = (result as { outcome?: { message?: string } | null } | null)
    ?.outcome;
  return outcome?.message ?? null;
};

const message = (err: unknown, fallback: string) =>
  err instanceof Error ? err.message : fallback;

// The offering the brief is about: the best-scoring judged offering among the chosen ones, or, with
// nothing chosen, the best judged offering overall. `fit` arrives best first.
export function focusOffering(
  fit: OfferingFit[] | null,
  chosen: string[],
): OfferingFit | null {
  if (!fit || fit.length === 0) return null;
  if (chosen.length === 0) return fit[0];
  return fit.find((f) => chosen.includes(f.product_id)) ?? null;
}

// Everything the brief shows about one opportunity beyond its assessment: the offering fits, the
// people for the focus offering (with a person's own overrides) and its recommendation. Slow work
// runs as a background job and is waited for here; stored results show straight away.
export function useBriefDetail(
  opportunityId: string,
  chosen: string[],
  onChange?: () => void,
  // Shown when working out the fit judged nothing. The Brief and the People tab word it
  // differently because only the Brief has the offering filter.
  emptyNotice = "Nothing could be judged this time. Pick offerings in the Offering filter, then work out the fit again.",
) {
  const [fit, setFit] = useState<OfferingFit[] | null>(null);
  const [contacts, setContacts] = useState<ContactRelevance[] | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [busy, setBusy] = useState<"analyse" | "recommend" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const gone = useRef(false);

  useEffect(() => {
    gone.current = false;
    return () => {
      gone.current = true;
    };
  }, [opportunityId]);

  const focus = useMemo(() => focusOffering(fit, chosen), [fit, chosen]);
  const focusId = focus?.product_id ?? null;

  const loadFit = useCallback(async () => {
    try {
      const rows = await fetchFit(opportunityId);
      setFit(rows);
      return rows;
    } catch (err) {
      setError(message(err, "could not load the offerings"));
      return null;
    }
  }, [opportunityId]);

  const loadContacts = useCallback(async () => {
    try {
      setContacts(await fetchContacts(opportunityId, focusId));
    } catch (err) {
      setError(message(err, "could not load the people"));
    }
  }, [opportunityId, focusId]);

  const loadRecommendations = useCallback(async () => {
    try {
      setRecommendations(await fetchOpportunityRecommendations(opportunityId));
    } catch {
      // Supplementary: the rest of the brief still works.
    }
  }, [opportunityId]);

  useEffect(() => {
    loadFit();
    loadRecommendations();
  }, [loadFit, loadRecommendations]);

  useEffect(() => {
    setContacts(null);
    loadContacts();
  }, [loadContacts]);

  async function runJob(
    kind: "analyse" | "recommend",
    start: () => Promise<{ job_id: string }>,
  ) {
    setBusy(kind);
    setError(null);
    setNotice(null);
    try {
      const { job_id } = await start();
      const job = await waitForJob(job_id, () => gone.current);
      if (job?.status === "failed")
        setError(job.error ?? "the work did not finish");
      const [rows] = await Promise.all([
        loadFit(),
        loadContacts(),
        loadRecommendations(),
      ]);
      if (kind === "analyse" && job?.status === "done" && rows?.length === 0)
        setNotice(jobOutcome(job.result) ?? emptyNotice);
      onChange?.();
    } catch (err) {
      setError(message(err, "could not start"));
    } finally {
      setBusy(null);
    }
  }

  // Work out the fit for the chosen offerings (or the best match when none are chosen).
  const analyse = (force = false) =>
    runJob("analyse", () => startAnalysis(opportunityId, chosen, force));

  const recommend = (productId: string, force = false) =>
    runJob("recommend", () =>
      startRecommendation(opportunityId, productId, force),
    );

  async function override(contactId: string, role: BuyingRole | "model") {
    setError(null);
    try {
      if (role === "model")
        await clearRelevance(opportunityId, contactId, focusId);
      else await setRelevance(opportunityId, contactId, focusId, role, null);
      await loadContacts();
      onChange?.();
    } catch (err) {
      setError(message(err, "could not save that"));
    }
  }

  const recommendation =
    recommendations.find((r) => r.product_id === focusId) ?? null;

  return {
    fit,
    focus,
    contacts,
    recommendation,
    busy,
    error,
    notice,
    analyse,
    recommend,
    override,
  };
}
