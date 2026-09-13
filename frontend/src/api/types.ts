export type CsvIngestionStarted = {
  ingestion_run_id: string;
  job_id: string;
};

export type JobStatus = {
  id: string;
  job_type: string;
  status: "pending" | "running" | "done" | "failed";
  progress: { done: number; total: number } | null;
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
};

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
  summary: { candidates_found: number; companies_created: number } | null;
  error: string | null;
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
};
