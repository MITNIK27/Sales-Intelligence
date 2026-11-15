import { apiDelete, apiGet, apiPost, apiPut } from "@/api/client";
import type {
  BuyingRole,
  CompanyOpportunity,
  ContactRelevance,
  JobStatus,
  OfferingFit,
  Recommendation,
} from "@/api/types";

export const fetchOpportunities = (companyId: string) =>
  apiGet<CompanyOpportunity[]>(`/companies/${companyId}/opportunities`);

export const createOpportunity = (
  companyId: string,
  areaLabel: string | null,
) =>
  apiPost<CompanyOpportunity>(`/companies/${companyId}/opportunities`, {
    area_label: areaLabel,
  });

export const addPerson = (
  companyId: string,
  p: {
    full_name: string;
    role_title: string;
    linkedin_url: string | null;
    email: string | null;
  },
) => apiPost<{ id: string }>(`/companies/${companyId}/contacts`, p);

export type RunOffering = { id: string; name: string; kind: string };

// The offerings chosen when a Market Discovery run was confirmed (empty for older runs).
export const fetchRunOfferings = (runId: string) =>
  apiGet<RunOffering[]>(`/market-discovery/${runId}/offerings`);

// `refresh` asks the model again and replaces the suggestions; without it, areas already suggested
// are returned and no model call is made.
export const suggestAreas = (companyId: string, refresh = false) =>
  apiPost<{ job_id: string }>(`/companies/${companyId}/opportunities/suggest`, {
    refresh,
  });

// Research what we could offer the company as a whole: its news, hiring and work in the areas we
// sell in, then every offering judged against it. Runs in the background.
export const researchOffers = (companyId: string, force = false) =>
  apiPost<{ job_id: string }>(`/companies/${companyId}/opportunities/offers`, {
    force,
  });

export const startAssessment = (opportunityId: string, force = false) =>
  apiPost<{ job_id: string }>(`/opportunities/${opportunityId}/assess`, {
    force,
  });

export const fetchJob = (jobId: string) => apiGet<JobStatus>(`/jobs/${jobId}`);

export const fetchFit = (opportunityId: string) =>
  apiGet<OfferingFit[]>(`/opportunities/${opportunityId}/fit`);

export const startAnalysis = (
  opportunityId: string,
  productIds: string[] = [],
  force = false,
) =>
  apiPost<{ job_id: string }>(`/opportunities/${opportunityId}/analyse`, {
    product_ids: productIds,
    with_contacts: true,
    force,
  });

export const fetchContacts = (
  opportunityId: string,
  productId: string | null,
) =>
  apiGet<ContactRelevance[]>(
    `/opportunities/${opportunityId}/contacts${productId ? `?product_id=${productId}` : ""}`,
  );

export const setRelevance = (
  opportunityId: string,
  contactId: string,
  productId: string | null,
  role: BuyingRole,
  note: string | null,
) =>
  apiPut<ContactRelevance>(
    `/opportunities/${opportunityId}/contacts/${contactId}/relevance`,
    {
      product_id: productId,
      role,
      note,
    },
  );

export const clearRelevance = (
  opportunityId: string,
  contactId: string,
  productId: string | null,
) =>
  apiDelete<void>(
    `/opportunities/${opportunityId}/contacts/${contactId}/relevance${productId ? `?product_id=${productId}` : ""}`,
  );

export const startRecommendation = (
  opportunityId: string,
  productId: string,
  force = false,
) =>
  apiPost<{ job_id: string }>(
    `/opportunities/${opportunityId}/recommendation`,
    {
      product_id: productId,
      force,
    },
  );

export const fetchOpportunityRecommendations = (opportunityId: string) =>
  apiGet<Recommendation[]>(`/opportunities/${opportunityId}/recommendations`);

const sleep = (ms: number) =>
  new Promise((resolve) => window.setTimeout(resolve, ms));

// Wait for a background job to finish. A failed poll is not fatal: the next one retries. Stops
// quietly (returns null) when the caller says it has gone away, for example the page was left.
export async function waitForJob(
  jobId: string,
  isCancelled: () => boolean,
  intervalMs = 1500,
): Promise<JobStatus | null> {
  for (;;) {
    await sleep(intervalMs);
    if (isCancelled()) return null;
    try {
      const job = await fetchJob(jobId);
      if (job.status === "done" || job.status === "failed") return job;
    } catch {
      // try again on the next tick
    }
  }
}
