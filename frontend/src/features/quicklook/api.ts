import type { KnowledgeRef } from "@/api/types";
import { apiPost } from "@/api/client";

export type Call = "yes" | "maybe" | "no" | "unclear";
export type OfferingBand = "strong" | "potential" | "weak";

export type QuickLookOffering = {
  product_id: string;
  name: string;
  band: OfferingBand;
  reason: string;
  quote: string | null;
  source_url: string | null;
  // Where the quote came from: "site", "news", "hiring" or "search"; and its date when stated.
  source_kind: string | null;
  source_date: string | null;
  // What we would offer them and which of their moves it builds on; only when proven.
  idea: string | null;
  why_now: string | null;
};

// Something the company is doing in an area we sell in, with the evidence behind it.
export type WorkingOn = {
  point: string;
  quote: string;
  source_url: string | null;
  source_kind: string | null;
  source_date: string | null;
};

export type Snapshot = {
  id: string;
  domain: string;
  name: string;
  what_they_do: string | null;
  industry: string | null;
  size_hint: string | null;
  relevance: string | null;
  call: Call;
  call_reason: string;
  offerings: QuickLookOffering[];
  working_on: WorkingOn[];
  focus: string | null;
  criteria: CriterionResult[];
  // Passages from our documents the model was shown, `cited` when the answer names them (Phase 8d).
  knowledge?: KnowledgeRef[];
  sources: { url: string; kind: string }[];
  updated_at: string;
  cached: boolean;
  // Set when the company is already in the companies list.
  existing_company_id: string | null;
  // Set when that company was marked not a fit: the reason the person gave.
  existing_company_dismissed_reason?: string | null;
};

export type Candidate = { name: string; domain: string; snippet: string };

export type QuickLookResponse = {
  status: "ready" | "needs_choice" | "not_found";
  snapshot: Snapshot | null;
  candidates: Candidate[];
  notes: string[];
};

export type QuickLookRequest = {
  // A company name or website, whichever the person typed.
  company?: string;
  // A website the person pasted or a candidate they chose.
  domain?: string;
  // Websites already rejected with "not this one".
  avoid?: string[];
  refresh?: boolean;
  // Show the candidates instead of picking one.
  always_ask?: boolean;
  // Optional extras: an area to research around, and the person's own criteria.
  focus?: string;
  criteria?: string[];
};

export type CriterionVerdict = "met" | "not_met" | "unknown";

export type CriterionResult = {
  name: string;
  verdict: CriterionVerdict;
  reason: string;
  quote: string | null;
  source_url: string | null;
};

export type SaveResponse = {
  company_id: string;
  created: boolean;
  job_id: string | null;
};

export function quickLook(body: QuickLookRequest): Promise<QuickLookResponse> {
  return apiPost<QuickLookResponse>("/quick-look", body);
}

export function saveSnapshot(
  snapshotId: string,
  goDeeper: boolean,
): Promise<SaveResponse> {
  return apiPost<SaveResponse>("/quick-look/save", {
    snapshot_id: snapshotId,
    go_deeper: goDeeper,
  });
}
