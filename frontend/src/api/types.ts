export type CsvIngestionStarted = {
  ingestion_run_id: string;
  job_id: string;
};

// `done`/`total` count whole stages for the auto pipeline; the extras describe the current one.
export type JobProgress = {
  done: number;
  total: number;
  detail?: string | null;
  // The last few things that really happened, oldest first.
  trail?: string[];
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

export type EnrichmentStatus =
  "never_enriched" | "pending" | "enriched" | "failed";

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
  // Set when a person marked the company not a fit (only listed with the Not a fit view).
  dismissed_at?: string | null;
  dismissed_reason?: string | null;
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
  channel_type: "email" | "phone" | "linkedin";
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
  // How sure the search was that they work here (0..1); null for people added by hand.
  confidence?: number | null;
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
  // Messages logged as sent to this person, and when the last one went out.
  touches_sent: number;
  last_sent_at: string | null;
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
  // What the person wants to know about this company, typed here or on the search that found it.
  criteria?: CompanyCriterion[];
  // Set when a person marked this company not a fit: why, and an optional note.
  dismissed_at?: string | null;
  dismissed_reason?: string | null;
  dismissed_note?: string | null;
  // What Quick Check said about this website, when it was ever looked up.
  quick_check?: QuickCheckNote | null;
  contacts: Contact[];
};

export type QuickCheckNote = {
  call: string;
  call_reason: string;
  relevance: string | null;
  updated_at: string;
};

// A company that has logged outreach or sent drafts, which hiding it would lose sight of.
export type CompanyHistory = {
  company_id: string;
  company_name: string;
  outreach_activities: number;
  sent_drafts: number;
};

export type DismissalCheckResult = { with_history: CompanyHistory[] };

export type CompanyDismissRequest = {
  company_ids: string[];
  reason: string;
  note: string | null;
  // The person has been told about the outreach on record and still wants it hidden.
  acknowledge_history: boolean;
};

export type CompanyDismissResult = {
  dismissed: number;
  already_dismissed: number;
  not_found: string[];
  // Left as they were: they have outreach on record and need the person's confirmation.
  needs_confirmation: CompanyHistory[];
};

export type CompanyCriterion = {
  name: string;
  description: string | null;
  must_have: boolean;
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
  // Role categories to treat as targets for this run only. Empty means every matched role counts.
  role_category_ids?: string[];
  // The criteria typed for this search. A
  // must-have drops a company that clearly fails it; nothing chosen means nothing is excluded.
  criteria?: {
    name?: string | null;
    description?: string | null;
    must_have: boolean;
  }[];
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
  provenance: Record<
    string,
    { source: string; confidence: number; fetched_at: string }
  >;
};

export type ScoreBreakdown = {
  components?: Record<
    string,
    { weight: number; value: number; points: number; note: string }
  >;
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
      not_checked?: number;
      criteria_chosen?: number;
      qualified_company_ids: string[];
      errors: { company_id: string; error: string }[];
    };

export type RoleClassificationStageResult =
  | { ran: false; skipped_reason: string }
  | {
      ran: true;
      companies_classified: number;
      errors: { company_id: string; error: string }[];
    };

export type DraftingStageResult =
  | { ran: false; skipped_reason: string }
  | {
      ran: true;
      drafts_generated: number;
      errors: { contact_id: string; error: string }[];
    };

export type AutoPipelineResult = {
  discovery: {
    candidates_found: number;
    companies_created: number;
    reused_from_index: number;
  };
  qualification: QualificationStageResult;
  ranking?: {
    ranked: number;
    top: { company_id: string; score: number; verdict: string }[];
  };
  role_classification: RoleClassificationStageResult;
  drafting: DraftingStageResult;
  capped: boolean;
};

export type ProductKind = "service" | "product";

export type Product = {
  id: string;
  name: string;
  description: string | null;
  kind: ProductKind;
  // "manual" = added by a person; "website" = imported from the InfoBeans site and approved.
  source: "manual" | "website";
  source_url: string | null;
  status: "active" | "archived";
  // Who buys and influences this offering; null until generated or written by hand.
  buyer_profile?: BuyerProfile | null;
  profile_status?: "generated" | "edited" | null;
  // True when a generated profile no longer matches the offering's current description.
  profile_stale?: boolean;
  created_at: string;
  updated_at: string;
};

// What a company is doing in one business area, with the evidence for it. Findings that could not
// be verified against their cited evidence are discarded before they get here.
export type OpportunityVerdict =
  "supported" | "emerging" | "weak" | "insufficient_evidence";

export type OpportunityFinding = {
  kind: string;
  statement: string;
  evidence: {
    record_id: string | null;
    field: string | null;
    kind: string;
    url: string | null;
    date: string | null;
    fetched_at: string | null;
    content_hash: string;
    quote: string;
  };
};

export type OpportunityAssessment = {
  id: string;
  version: number;
  verdict: OpportunityVerdict;
  summary: string;
  findings: OpportunityFinding[];
  not_found: string[];
  dropped_count: number;
  evidence_count: number;
  model_used: string;
  created_at: string;
};

// What one research collector (news, hiring or web) did last time for an opportunity.
export type ResearchEntry = {
  at?: string;
  found: number;
  searched: string[];
  error: string | null;
  // People search only: where the results were lost, in one sentence.
  summary?: string;
  // Hiring only: every open role on the board, the board used, and the counts over time.
  total_open?: number | null;
  board?: string | null;
  snapshots?: { at: string; total: number | null; matching: number }[];
};

export type CompanyOpportunity = {
  id: string;
  company_id: string;
  area_key: string;
  area_label: string;
  origin: string;
  status: "suggested" | "active" | "archived";
  suggestion_reason: string | null;
  // Why a suggested area is listed: searched for in Market Discovery, the evidence points to it, or
  // it is a next best area. `suggestion_rank` is its place in the list (lower is first).
  suggestion_source?: "searched" | "evidence" | "next_best" | null;
  suggestion_rank?: number | null;
  // Passages from our documents the suggestion cited (Phase 8d).
  suggestion_knowledge_refs?: KnowledgeRef[] | null;
  industry_context: string | null;
  created_at: string;
  assessment: OpportunityAssessment | null;
  research?: Record<string, ResearchEntry> | null;
};

// What a company was searched for in Market Discovery and how each offering searched for fits,
// kept on file so the Brief can show it without running anything.
export type SearchContextOffering = {
  product_id: string;
  name: string;
  kind: string;
  area_label: string;
  area_id: string | null;
  area_researched: boolean;
  state: "judged" | "working" | "not_checked";
  band: FitBand | null;
  band_label: string | null;
  score: number | null;
  reasoning: string | null;
  evidence: {
    quote: string;
    kind?: string;
    date?: string | null;
    url?: string | null;
    content_hash?: string;
  }[];
};

export type SearchContextRun = {
  run_id: string;
  label: string;
  created_at: string;
  searched: {
    industry_keywords: string[];
    location: string | null;
    employee_size_range: string | null;
  };
  criteria: string[];
  offerings: SearchContextOffering[];
  // "chosen" on the form, or "keywords": matched from the words that were searched.
  offerings_found_by: "chosen" | "keywords";
};

export type SearchContext = { runs: SearchContextRun[] };

export type FitBand = "strong" | "potential" | "weak" | "insufficient_evidence";

// How well one offering fits a company in an area. The band comes from rules over `factors`; every
// citation in `evidence` was checked to be a real quote from its source.
export type OfferingFit = {
  product_id: string;
  product_name: string;
  product_kind: ProductKind;
  band: FitBand;
  score: number;
  reasoning: string;
  factors: {
    verified_evidence: number;
    area_alignment: boolean;
    keyword_hits: number;
    assessment_verdict: string | null;
    dropped_citations: number;
  };
  evidence: OpportunityFinding["evidence"][];
  needs_review: boolean;
  // Passages from our documents the model was shown about this offering (Phase 8d).
  knowledge_refs?: KnowledgeRef[] | null;
  created_at: string;
};

// A passage from our own documents that a model was shown. `cited` is true when its text names the
// label (K1, K2...), so the person can see which document a claim about an offering came from.
export type KnowledgeRef = {
  label: string;
  chunk_id: string;
  document_id: string;
  document_name: string;
  version: number;
  locator: string;
  cited?: boolean;
};

export type BuyingRole =
  "decision_maker" | "influencer" | "user" | "not_relevant";

// A person and the part they play for an opportunity. `source` says who decided: the model or a
// person; when a person overrode the model, the model's own view is kept in model_role.
export type ContactRelevance = {
  contact_id: string;
  full_name: string | null;
  role_title: string | null;
  seniority: string | null;
  contact_needs_review: boolean;
  role: BuyingRole | null;
  function: string | null;
  reasoning: string | null;
  confidence: "low" | "medium" | "high" | null;
  needs_review: boolean;
  source: "model" | "human" | null;
  note: string | null;
  model_role: BuyingRole | null;
  model_reasoning: string | null;
};

export type BuyerProfile = {
  buyer_functions: string[];
  influencer_functions: string[];
  problems: string[];
  keywords: string[];
  area_tags: string[];
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
  kind?: ProductKind;
};

export type ProductUpdateRequest = {
  name?: string;
  description?: string | null;
  kind?: ProductKind;
  status?: "active" | "archived";
};

export type OfferingProposalChange = "new" | "changed" | "removed";

// Something found on the InfoBeans website that nobody has approved yet.
export type OfferingProposal = {
  id: string;
  change: OfferingProposalChange;
  status: "pending" | "approved" | "rejected";
  kind: ProductKind;
  name: string;
  description: string | null;
  source_url: string;
  product_id: string | null;
  detected_at: string;
  // What the live offering says today, for "changed" and "removed".
  current: {
    name: string;
    description: string | null;
    kind: ProductKind;
  } | null;
  // Which lane found it; blog-post finds ("post") are suggestions, not part of the main review.
  origin: "site" | "extra" | "post" | "menu";
  // The start of the page the description was written from, for checking it on the spot.
  source_excerpt: string | null;
  // Anything in the description the page does not back up.
  grounding_flags: string[] | null;
  // A live offering or another waiting proposal this may be the same thing as.
  possible_duplicate: string | null;
};

export type OfferingPageVerdict = "offering" | "not_offering" | "failed";

export type OfferingCoveragePage = {
  url: string;
  title: string | null;
  lane: "site" | "extra" | "post" | "menu";
  verdict: OfferingPageVerdict;
  reason: string | null;
  lastmod: string | null;
  last_checked_at: string | null;
  force_extract: boolean;
};

export type OfferingMenuStatus =
  "covered" | "judged_not_offering" | "unreadable" | "missing";

export type OfferingMenuItem = {
  group: string;
  label: string;
  url: string;
  status: OfferingMenuStatus;
};

export type OfferingCoverage = {
  summary: {
    total: number;
    offering: number;
    not_offering: number;
    failed: number;
  };
  pages: OfferingCoveragePage[];
  // null until a check has read the website menu.
  menu: OfferingMenuItem[] | null;
  menu_error: string | null;
};

export type OfferingProposalList = {
  items: OfferingProposal[];
  total: number;
};

export type OfferingSyncStatus = {
  running: boolean;
  job_id: string | null;
  progress: { done?: number; total?: number } | null;
  last_checked_at: string | null;
  last_result: {
    new?: number;
    changed?: number;
    removed?: number;
    failed?: number;
    answered_by?: string[];
  } | null;
  last_error: string | null;
  pending_count: number;
};

// "not_checked": nothing was decided about the company (no criteria were chosen for the run, or
// it was an informational check). It is never shown as Qualified or Not qualified.
export type QualificationVerdict =
  "qualified" | "not_qualified" | "could_not_determine" | "not_checked";

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
  // The area this check was asked to judge fit around; null means a general judgment.
  focus?: string | null;
  created_at: string;
};

export type AdhocQualificationCheckRequest = {
  // A company name or its website, whichever the person typed.
  company: string;
  focus?: string | null;
  // Offerings to judge fit for; empty means only the single best match.
  product_ids?: string[];
};

export type FramingStyle = "business" | "technical";

export const FRAMING_STYLES: FramingStyle[] = ["business", "technical"];

export type RoleCategory = {
  id: string;
  name: string;
  description: string | null;
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
  is_active?: boolean;
  framing_style?: FramingStyle;
};

export type RoleCategoryUpdateRequest = {
  name?: string;
  description?: string | null;
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
  knowledge_refs?: KnowledgeRef[] | null;
  created_at: string;
};

export type RecommendationGenerateRequest = {
  product_id: string;
  contact_id?: string | null;
};

export type OutreachChannel = "email" | "linkedin";

export type OutreachActivityType = "sent" | "response_received";

export const OUTREACH_CHANNELS: OutreachChannel[] = ["email", "linkedin"];
export const OUTREACH_ACTIVITY_TYPES: OutreachActivityType[] = [
  "sent",
  "response_received",
];

// Shared between OutreachChannel and FollowUpChannel (both "email" | "linkedin") — a single
// label source so a rendered dropdown always reads "LinkedIn" (correct brand casing) rather
// than a naively-capitalized "Linkedin".
export const CHANNEL_LABELS: Record<"email" | "linkedin", string> = {
  email: "Email",
  linkedin: "LinkedIn",
};

// What a reply said, chosen by the rep.
export type OutreachOutcome =
  "interested" | "not_now" | "not_interested" | "referred" | "out_of_office";

export const OUTREACH_OUTCOMES: OutreachOutcome[] = [
  "interested",
  "not_now",
  "not_interested",
  "referred",
  "out_of_office",
];

export type OutreachActivity = {
  id: string;
  contact_id: string;
  draft_id: string | null;
  channel: OutreachChannel;
  activity_type: OutreachActivityType;
  template_variant: string | null;
  notes: string | null;
  outcome: OutreachOutcome | null;
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
  // When it really happened; leave out for now.
  occurred_at?: string | null;
  // What a reply said (replies only).
  outcome?: OutreachOutcome | null;
  // For a reply that asks to wait: business days until the next follow-up.
  follow_up_in_business_days?: number | null;
};

export type LogOutreachActivityResponse = {
  activity: OutreachActivity;
  contact: Contact;
};

export type DraftType =
  "first_touch" | "follow_up" | "follow_up_2" | "follow_up_3";
export type DraftStatus = "draft" | "sent" | "discarded";

export const DRAFT_TYPES: DraftType[] = [
  "first_touch",
  "follow_up",
  "follow_up_2",
  "follow_up_3",
];

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
  grounding_flags?: string[] | null;
  // What the rep last asked for when rewriting it, and how many earlier versions Undo can restore.
  instruction?: string | null;
  revision_count?: number;
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
  setup: {
    products: number;
    active_role_categories: number;
  };
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
  grounding_flags?: string[] | null;
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

export type UsageLine = {
  provider: string;
  task: string;
  calls: number;
  errors: number;
  tokens_in: number;
  tokens_out: number;
  units: number;
  est_cost_usd: number;
};

export type UsageSummary = {
  days: number;
  lines: UsageLine[];
  total_est_cost_usd: number;
};

// --- Documents (Phase 8b): decks, PDFs and notes about what we sell -------------------------------
export type DocumentStatus = "queued" | "processing" | "ready" | "failed";
export type DocumentMediaType = "pdf" | "pptx" | "docx" | "md" | "txt";

export type DocumentsStatusInfo = {
  enabled: boolean;
  max_upload_mb: number;
  accepted_extensions: string[];
  // True when pictures and scanned pages will be described by a model.
  vision_enabled: boolean;
  // Passages are also found by meaning (needs the setting and a Gemini key), not only by words.
  meaning_search_enabled: boolean;
};

export type LibraryDocument = {
  id: string;
  name: string;
  original_filename: string;
  media_type: DocumentMediaType;
  size_bytes: number;
  // The state of the newest version.
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  chunk_count: number;
  // Passages that have a vector for meaning search; fewer than chunk_count while indexing.
  indexed_chunks: number;
  version: number;
  version_count: number;
  // Some version has been read and is the one search uses.
  is_searchable: boolean;
  offerings: { id: string; name: string }[];
  assets: { described: number; skipped: number; failed: number };
  // The uploaded file is still held, so it can be read again without uploading.
  can_reprocess: boolean;
  job_id: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentVersionInfo = {
  id: string;
  version: number;
  original_filename: string;
  media_type: DocumentMediaType;
  size_bytes: number;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  chunk_count: number;
  is_current: boolean;
  created_at: string;
  processed_at: string | null;
};

export type DocumentEvent = {
  step: string;
  status: "ok" | "warning" | "error";
  message: string;
  duration_ms: number | null;
  created_at: string;
};

export type DocumentDetailData = LibraryDocument & {
  versions: DocumentVersionInfo[];
  events: DocumentEvent[];
};

export type DocumentPageText = {
  position: number;
  locator: string;
  heading_path: string | null;
  text: string;
};

// A picture, chart, table or scanned page that a model described. These words were written by the
// model named here, not by whoever wrote the document.
export type DocumentAssetInfo = {
  position: number;
  locator: string;
  kind: "image" | "table" | "scanned_page";
  status: "described" | "skipped" | "failed";
  description: string | null;
  note: string | null;
  provider: string | null;
  model_used: string | null;
  prompt_version: string | null;
  est_cost_usd: number | null;
};

export type DocumentPagesData = {
  version: number;
  total: number;
  pages: DocumentPageText[];
  assets: DocumentAssetInfo[];
};

export type DocumentSearchHit = {
  chunk_id: string;
  document_id: string;
  document_name: string;
  version: number;
  locator: string;
  heading_path: string | null;
  text: string;
  offerings: { id: string; name: string }[];
  score: number;
  // Closeness to the question by meaning (0 to 1); null when found by words only.
  similarity: number | null;
  word_match: boolean;
  about_offering: boolean;
};

export type DocumentSearchResult = {
  question: string;
  mode: "meaning_and_words" | "words_only";
  note: string | null;
  indexed_passages: number;
  total_passages: number;
  hits: DocumentSearchHit[];
};
