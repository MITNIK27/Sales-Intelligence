export type CsvIngestionStarted = {
  ingestion_run_id: string;
  job_id: string;
};

// `done`/`total` count whole stages for the auto pipeline; the extras describe the current one.
export type JobProgress = {
  done: number;
  total: number;
  detail?: string | null;
  stage?: number;
  stage_name?: string;
  stage_done?: number;
  stage_total?: number;
  enriched?: number;
  failed?: number;
};

export type JobStatus = {
  id: string;
  job_type: string;
  status: "pending" | "running" | "done" | "failed";
  progress: JobProgress | null;
  result: {
    companies_created: number;
    companies_updated: number;
    contacts_created: number;
    rows_skipped: number;
    errors: { row_number: number; error: string }[];
  } | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type EnrichmentStatus = "never_enriched" | "pending" | "enriched" | "failed";

export const ENRICHMENT_STATUSES: EnrichmentStatus[] = [
  "never_enriched",
  "pending",
  "enriched",
  "failed",
];

export type CompanyListItem = {
  id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  contact_count: number;
  enrichment_status: EnrichmentStatus;
  needs_review: boolean;
  qualification_verdict: QualificationVerdict | null;
  created_at: string;
  last_enriched_at: string | null;
};

export type CompanySortField =
  | "name"
  | "created_at"
  | "last_enriched_at"
  | "enrichment_status"
  | "qualification";
export type SortDirection = "asc" | "desc";

export type CompanyList = {
  items: CompanyListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type ContactChannel = {
  id: string;
  channel_type: "email" | "phone";
  value: string;
  verification_status: string;
};

export type TrackingStatus =
  | "not_contacted"
  | "contacted"
  | "follow_up_scheduled"
  | "responded"
  | "not_a_fit";

// email | linkedin only — no cold calling for international contacts (per the meeting this
// tracker automates). Shared with OutreachActivity's channel below.
export type FollowUpChannel = "email" | "linkedin";

export const TRACKING_STATUSES: TrackingStatus[] = [
  "not_contacted",
  "contacted",
  "follow_up_scheduled",
  "responded",
  "not_a_fit",
];

export const FOLLOW_UP_CHANNELS: FollowUpChannel[] = ["email", "linkedin"];

export type Contact = {
  id: string;
  full_name: string | null;
  role_title: string | null;
  status: TrackingStatus;
  next_follow_up_at: string | null;
  next_follow_up_channel: FollowUpChannel | null;
  timezone: string | null;
  needs_review: boolean;
  needs_review_reason: string | null;
  channels: ContactChannel[];
};

export type ContactTrackingUpdate = {
  status?: TrackingStatus | null;
  next_follow_up_at?: string | null;
  next_follow_up_channel?: FollowUpChannel | null;
  timezone?: string | null;
};

export type CompanySummary = {
  id: string;
  name: string;
  domain: string | null;
};

export type FollowUpItem = {
  id: string;
  full_name: string | null;
  role_title: string | null;
  status: TrackingStatus;
  next_follow_up_at: string | null;
  next_follow_up_channel: FollowUpChannel | null;
  company: CompanySummary;
};

export type CompanyDetail = {
  id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  employee_count_range: string | null;
  description: string | null;
  enrichment_status: EnrichmentStatus;
  needs_review: boolean;
  needs_review_reason: string | null;
  last_enriched_at: string | null;
  enrichment_error: string | null;
  contacts: Contact[];
};

export type CompanyConfirmRequest = {
  product_ids?: string[];
};

// role_classification/draft are best-effort resume results the backend attempts synchronously
// after clearing needs_review — the page just needs the updated company back out of this.
export type CompanyConfirmResult = {
  company: CompanyDetail;
  role_classification: Record<string, unknown>;
  drafting: Record<string, unknown>;
};

export type ScrapeJobStarted = {
  job_id: string;
};

export type ScrapeAllStarted = {
  enqueued_count: number;
};

export type Signal = {
  signal_type: "news" | "job_posting";
  text: string;
  url: string;
  date: string | null;
  fetched_at: string;
  summary?: string | null;
  provider?: string | null;
};

export type ParsedFieldConfidence = "confident" | "could_not_determine";

export type ParsedField<T> = {
  value: T;
  confidence: ParsedFieldConfidence;
};

export type MarketCriteriaParsed = {
  industry_keywords: ParsedField<string[]>;
  location: ParsedField<string | null>;
  employee_size_range: ParsedField<string | null>;
};

export type MarketDiscoveryParsed = {
  ingestion_run_id: string;
  parsed_fields: MarketCriteriaParsed;
};

export type MarketDiscoveryConfirmRequest = {
  industry_keywords: string[];
  location: string | null;
  employee_size_range: string | null;
  // Which product(s) the auto-pipeline's drafting stage may pitch. Empty (and the org doesn't
  // have exactly one product to default to) means drafting reports itself skipped rather than
  // guessing which product to pitch — discovery/qualification/role classification still run. More
  // than one product means the draft generator itself picks whichever single one best fits each
  // company/contact.
  product_ids?: string[];
  // Hard requirements for this search only; each is judged for every company with evidence.
  market_fit_criteria?: { name: string; description: string | null }[];
};

export type MarketDiscoveryStarted = {
  job_id: string;
};

export type MarketDiscoveryRun = {
  id: string;
  status: "pending" | "running" | "done" | "failed" | "awaiting_confirmation";
  raw_input: string | null;
  parsed_fields: MarketCriteriaParsed | null;
  confirmed_at: string | null;
  summary: {
    candidates_found: number;
    companies_created: number;
    reused_from_index?: number;
    // Which CompanyDataProvider setting produced this run's firmographics, and how enrichment
    // went — recorded as data so a run can be judged (e.g. scraper vs context.dev) afterwards.
    company_data_source?: string;
    enrichment?: {
      enriched: number;
      failed: number;
      industry_filled: number;
      by_source: Record<string, number>;
      // Provider branches that errored without failing the company, e.g. { signals: 2 }.
      branch_errors?: Record<string, number>;
    };
    // Paid-provider spend for the run; null/absent when the scraper alone was used.
    context_dev?: {
      credits_used: number;
      credit_ceiling: number;
      budget_exhausted: boolean;
      skipped_sufficient?: number;
    } | null;
    // The discovery funnel: how many raw search hits came back, how many the LLM extracted as
    // named-entity candidates, how many it accepted as real/on-target, and (when fewer were
    // accepted than extracted) a capped sample of why specific candidates were rejected — lets a
    // 0-candidate run explain itself instead of just reporting a count.
    raw_results?: number;
    extracted?: number;
    accepted?: number;
    rejected?: number;
    rejected_samples?: { name: string; reasoning: string }[];
  } | null;
  error: string | null;
};

// The rep-facing result of a run (GET /market-discovery/{id}/companies): `ready` rows are
// qualified companies that have a primary-target contact and a draft; `not_shown` rows carry
// a one-line `skip_reason` instead.
export type WorklistDraft = {
  draft_id: string;
  subject: string | null;
  body: string;
  status: DraftStatus;
};

// A candidate contact at a ready company. `linkedin_url`/`email` are null when nothing was found
// (shown as "not found", never guessed). `needs_review` means found via search and not yet
// confirmed: the rep's one click both confirms the person and writes the draft.
export type WorklistContact = {
  contact_id: string;
  full_name: string | null;
  role_title: string | null;
  category: string | null;
  linkedin_url: string | null;
  email: string | null;
  needs_review: boolean;
  needs_review_reason: string | null;
  draft: WorklistDraft | null;
  confidence: number | null;
  source: string | null;
};

export type WorklistRow = {
  company_id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  employee_count_range: string | null;
  description: string | null;
  data_source: "context.dev" | "scraper" | "none";
  verdict: QualificationVerdict | null;
  why: string | null;
  candidates: WorklistContact[];
  skip_reason: string | null;
  criteria: WorklistCriterion[];
  confidence: number | null;
  // Priority Score 0-100 (higher = stronger opportunity) and how it was made up.
  priority_score: number | null;
  score_breakdown: ScoreBreakdown | null;
  // Where industry / size / description came from, e.g. { industry: { source: "contextdev:brand" } }.
  provenance: Record<string, { source: string; confidence: number; fetched_at: string }>;
};

export type ScoreBreakdown = {
  components?: Record<string, { weight: number; value: number; points: number; note: string }>;
  evidence_factor?: number;
  raw?: number;
  excluded?: string;
};

export type WorklistCriterion = {
  name: string;
  status: "PASS" | "FAIL" | "UNKNOWN";
  hard: boolean;
  scope: "run" | "org";
  reasoning: string | null;
  evidence_quote: string | null;
  source: string | null;
  url: string | null;
  confidence: number | null;
};

export type MarketDiscoveryWorklist = {
  ready: WorklistRow[];
  not_shown: WorklistRow[];
};

// The confirm step now enqueues a single `auto_pipeline` job — its `JobStatus.result` carries
// this four-stage breakdown instead of the old discovery-only summary. Each stage after
// discovery either ran, or was skipped with a clear reason (missing prerequisites), never
// silently omitted.
export type QualificationStageResult =
  | { ran: false; skipped_reason: string }
  | {
      ran: true;
      qualified: number;
      not_qualified: number;
      could_not_determine: number;
      qualified_company_ids: string[];
      errors: { company_id: string; error: string }[];
    };

export type RoleClassificationStageResult =
  | { ran: false; skipped_reason: string }
  | { ran: true; companies_classified: number; errors: { company_id: string; error: string }[] };

export type DraftingStageResult =
  | { ran: false; skipped_reason: string }
  | { ran: true; drafts_generated: number; errors: { contact_id: string; error: string }[] };

export type AutoPipelineResult = {
  discovery: {
    candidates_found: number;
    companies_created: number;
    reused_from_index: number;
  };
  qualification: QualificationStageResult;
  ranking?: { ranked: number; top: { company_id: string; score: number; verdict: string }[] };
  role_classification: RoleClassificationStageResult;
  drafting: DraftingStageResult;
  capped: boolean;
};

export type Product = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductList = {
  items: Product[];
  total: number;
  limit: number;
  offset: number;
};

export type ProductCreateRequest = {
  name: string;
  description?: string | null;
};

export type ProductUpdateRequest = {
  name?: string;
  description?: string | null;
};

export type QualificationCriterion = {
  id: string;
  name: string;
  description: string | null;
  is_disqualifying: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type QualificationCriterionList = {
  items: QualificationCriterion[];
  total: number;
  limit: number;
  offset: number;
};

export type QualificationCriterionCreateRequest = {
  name: string;
  description?: string | null;
  is_disqualifying?: boolean;
  is_active?: boolean;
};

export type QualificationCriterionUpdateRequest = {
  name?: string;
  description?: string | null;
  is_disqualifying?: boolean;
  is_active?: boolean;
};

export type QualificationVerdict = "qualified" | "not_qualified" | "could_not_determine";

export type QualificationCriterionResultEntry = {
  criterion_id: string;
  criterion_name: string;
  is_disqualifying: boolean;
  verdict: "met" | "not_met" | "could_not_determine";
  reasoning: string;
};

export type QualificationResult = {
  id: string;
  company_id: string;
  overall_verdict: QualificationVerdict;
  criteria_results: QualificationCriterionResultEntry[];
  model_used: string;
  created_at: string;
};

export type AdhocQualificationCheckRequest = {
  name?: string | null;
  domain?: string | null;
};

export type FramingStyle = "business" | "technical";

export const FRAMING_STYLES: FramingStyle[] = ["business", "technical"];

export type RoleCategory = {
  id: string;
  name: string;
  description: string | null;
  is_primary_target: boolean;
  is_active: boolean;
  framing_style: FramingStyle;
  created_at: string;
  updated_at: string;
};

export type RoleCategoryList = {
  items: RoleCategory[];
  total: number;
  limit: number;
  offset: number;
};

export type RoleCategoryCreateRequest = {
  name: string;
  description?: string | null;
  is_primary_target?: boolean;
  is_active?: boolean;
  framing_style?: FramingStyle;
};

export type RoleCategoryUpdateRequest = {
  name?: string;
  description?: string | null;
  is_primary_target?: boolean;
  is_active?: boolean;
  framing_style?: FramingStyle;
};

export type RolePriority = "primary" | "secondary" | "not_relevant";

export type RoleRelevanceResult = {
  id: string;
  company_id: string;
  contact_id: string;
  matched_category_id: string | null;
  matched_category_name: string | null;
  is_primary_target: boolean;
  matched_category_framing_style: FramingStyle | null;
  priority: RolePriority;
  reasoning: string;
  model_used: string;
  created_at: string;
};

export type Recommendation = {
  id: string;
  company_id: string;
  contact_id: string | null;
  product_id: string;
  pitch_summary: string;
  why_this_company: string;
  talking_points: string[];
  model_used: string;
  created_at: string;
};

export type RecommendationGenerateRequest = {
  product_id: string;
  contact_id?: string | null;
};

export type OutreachChannel = "email" | "linkedin";

export type OutreachActivityType = "sent" | "response_received";

export const OUTREACH_CHANNELS: OutreachChannel[] = ["email", "linkedin"];
export const OUTREACH_ACTIVITY_TYPES: OutreachActivityType[] = ["sent", "response_received"];

// Shared between OutreachChannel and FollowUpChannel (both "email" | "linkedin") — a single
// label source so a rendered dropdown always reads "LinkedIn" (correct brand casing) rather
// than a naively-capitalized "Linkedin".
export const CHANNEL_LABELS: Record<"email" | "linkedin", string> = {
  email: "Email",
  linkedin: "LinkedIn",
};

export type OutreachActivity = {
  id: string;
  contact_id: string;
  draft_id: string | null;
  channel: OutreachChannel;
  activity_type: OutreachActivityType;
  template_variant: string | null;
  notes: string | null;
  occurred_at: string;
  created_at: string;
};

export type LogOutreachActivityRequest = {
  channel: OutreachChannel;
  activity_type: OutreachActivityType;
  template_variant?: string | null;
  notes?: string | null;
  urgent?: boolean;
  draft_id?: string | null;
};

export type LogOutreachActivityResponse = {
  activity: OutreachActivity;
  contact: Contact;
};

export type DraftType = "first_touch" | "follow_up";
export type DraftStatus = "draft" | "sent" | "discarded";

export const DRAFT_TYPES: DraftType[] = ["first_touch", "follow_up"];

export type Draft = {
  id: string;
  company_id: string;
  contact_id: string;
  product_id: string;
  recommendation_id: string | null;
  draft_type: DraftType;
  channel: OutreachChannel;
  subject: string | null;
  body: string;
  status: DraftStatus;
  model_used: string;
  created_at: string;
  updated_at: string;
};

export type DraftGenerateRequest = {
  contact_id: string;
  product_id: string;
  draft_type: DraftType;
};

export type DraftUpdateRequest = {
  subject?: string | null;
  body?: string | null;
};

export type NeedsReviewItem = {
  entity_type: "company" | "contact";
  company_id: string;
  company_name: string;
  contact_id: string | null;
  contact_name: string | null;
  reason: string;
  flagged_at: string;
  contact_title?: string | null;
  contact_email?: string | null;
  contact_linkedin?: string | null;
  contact_source?: string | null;
  contact_confidence?: number | null;
  company_domain?: string | null;
};

export type BulkConfirmRequest = {
  company_ids: string[];
  contact_ids: string[];
  product_ids?: string[];
};

export type BulkConfirmStarted = {
  job_id: string;
};

export type BulkConfirmResult = {
  companies_confirmed: number;
  contacts_confirmed: number;
  company_results: Record<string, unknown>[];
};

// --- Dashboard (GET /dashboard/overview, GET /dashboard/runs) — read-only views over searches ---

export type DashboardKpis = {
  searches: number;
  companies: number;
  fit: number;
  needs_closer_look: number;
  rejected: number;
  contacts: number;
  likely_decision_makers: number;
  drafts_to_review: number;
  drafts_sent: number;
  credits_used: number;
};

export type DashboardFunnelStage = {
  key: string;
  label: string;
  count: number;
  percent_of_previous: number | null;
};

export type DashboardRequirement = {
  name: string;
  scope: "run" | "org";
  hard: boolean;
  meets: number;
  couldnt_verify: number;
  doesnt_meet: number;
  drafts_for_meeting: number;
};

export type DashboardTopCompany = {
  company_id: string;
  name: string;
  domain: string | null;
  score: number | null;
  verdict: QualificationVerdict | null;
  reason: string | null;
};

export type DashboardAttentionItem = {
  key: string;
  label: string;
  count: number;
  href: string;
};

export type DashboardActivityEvent = {
  at: string;
  kind: "search" | "draft" | "outreach" | "failure";
  text: string;
  run_id: string | null;
  company_id: string | null;
};

export type DashboardHealth = {
  credits_used: number;
  credit_ceiling: number | null;
  budget_exhausted: boolean;
  companies_needing_no_paid_lookup: number;
  enrichment_failed: number;
  provider_errors: Record<string, number>;
  notes: string[];
};

export type DashboardRunHeader = {
  run_id: string;
  title: string;
  summary: string;
  status: string;
  created_at: string;
  error: string | null;
  data_source: string | null;
  pipeline: Record<string, unknown> | null;
  progress: Record<string, unknown> | null;
};

export type DashboardOverview = {
  scope: "all" | "search";
  period: "7d" | "30d" | "all";
  headline: string;
  kpis: DashboardKpis;
  funnel: DashboardFunnelStage[];
  requirements: DashboardRequirement[];
  top_companies: DashboardTopCompany[];
  attention: DashboardAttentionItem[];
  activity: DashboardActivityEvent[];
  health: DashboardHealth;
  setup: { products: number; active_criteria: number; active_role_categories: number };
  run: DashboardRunHeader | null;
  searches: { run_id: string; label: string; created_at: string }[];
};

export type DashboardRunStats = {
  run_id: string;
  title: string;
  summary: string;
  status: string;
  created_at: string;
  error: string | null;
  companies: number;
  fit: number;
  needs_closer_look: number;
  rejected: number;
  contacts: number;
  drafts: number;
  top_score: number | null;
  credits_used: number | null;
};

export type DashboardRunList = {
  items: DashboardRunStats[];
  total: number;
  limit: number;
  offset: number;
};

// GET /drafts — every draft across companies, for the Drafts review page.
export type DashboardDraftItem = {
  id: string;
  company_id: string;
  company_name: string;
  contact_id: string;
  contact_name: string | null;
  contact_role: string | null;
  draft_type: DraftType;
  channel: OutreachChannel;
  subject: string | null;
  body: string;
  status: DraftStatus;
  model_used: string;
  created_at: string;
  updated_at: string;
};

export type DashboardDraftList = {
  items: DashboardDraftItem[];
  total: number;
  limit: number;
  offset: number;
  counts: { draft: number; sent: number; discarded: number };
};
