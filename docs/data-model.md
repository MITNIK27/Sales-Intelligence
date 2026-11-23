# Data Model

_Last updated: 2026-11-16._

## Entities

### Organization (tenant)
The owning org. Only one exists today (internal use), but every other entity is scoped to an
`organization_id` from the start so multi-tenancy doesn't require a later migration.

- `id`, `name`, `created_at`

### User
A person who signs in. Sign-in is Firebase Authentication (Phase 8): Firebase holds the credentials,
this table holds the person, linked by `firebase_uid`. No password is stored. People are disabled,
not deleted, so their decisions keep pointing at them. Not used by the app until sign-in is built.

- `id`, `organization_id` (FK), `firebase_uid` (unique), `email` (unique), `display_name` (nullable),
  `role` (`admin` | `manager` | `rep`), `status` (`active` | `disabled`), `last_sign_in_at`
  (nullable), `created_at`, `updated_at`

### Product (shown in the app as "Our Offerings")
The org's own catalog of what it sells, so the recommendation and drafting layers have something
concrete to pitch. The table and API path keep the name `products`; only the wording in the app is
"offerings". An offering is either typed by hand (`source = manual`) or imported from the company
website and approved by a person (`source = website`). A website offering is never changed or
archived except by approving a proposal (see `OfferingProposal`). Removal means `status =
archived`, never a delete, because drafts and recommendations reference it. `kind` decides how a
draft pitches it: a product may offer a walkthrough, a service a short conversation.

- `id`, `organization_id` (FK), `name`, `description`, `kind` (`service` | `product`, default
  `product`), `source` (`manual` | `website`), `source_url` (nullable, unique per organization when
  set), `source_hash` (hash of the page text it was read from), `status` (`active` | `archived`),
  `last_seen_at`, `buyer_profile`, `profile_status`, `profile_hash`, `profile_source_hash`,
  `created_at`, `updated_at`

`buyer_profile` (JSON, nullable) says who buys and influences the offering: `buyer_functions`,
`influencer_functions`, `problems`, `keywords` and `area_tags`. It describes business functions, not
job titles, is generated once from the offering's description and is editable on the Our Offerings
page. `profile_status` is `generated` or `edited` (a person's edit is never called stale);
`profile_hash` fingerprints the profile and is part of the cache key for anything judged with it;
`profile_source_hash` fingerprints the name, description and type it was generated from, so a
changed description marks a generated profile as possibly out of date.

### OfferingProposal
What the website importer found and a person has not yet decided on. The importer only ever writes
these rows; approving one is the only path that creates, changes or archives a `Product`. Pending
removal proposals are the importer's own staging rows and are withdrawn automatically when the page
turns out to be alive.

- `id`, `organization_id` (FK), `product_id` (FK, null for a new offering), `change` (`new` |
  `changed` | `removed`), `status` (`pending` | `approved` | `rejected`), `kind`, `name`,
  `description`, `source_url`, `content_hash`, `origin` (`site` | `extra` | `post` | `menu`),
  `source_excerpt` (the page text it came from, for comparison), `grounding_flags` (wording the
  grounding check could not find on the page), `detected_at`, `decided_at`

### OfferingPage (the page ledger)
One row per website page ever considered, so an unchanged page costs no scrape and no model call
on the next check. Addresses are stored in one canonical form (lowercase host, no `www`, no
fragment or query, no trailing slash except the root).

- `id`, `organization_id` (FK), `url` (unique per organization), `lane` (`site` | `extra` | `post` |
  `menu`), `title`, `lastmod` (from the sitemap), `content_hash`, `verdict` (`offering` |
  `not_offering` | `failed`), `reason`, `last_fetched_at`, `last_checked_at`, `force_extract`
  (set when a person asks for a page to be read as an offering), `extra` (JSONB)

### IngestionRun (job)
One CSV upload or one Market Discovery request. Tracks the batch through the pipeline.

- `id`, `organization_id` (FK), `source_type` (`csv` | `market_discovery`), `status`,
  `created_by_user_id`, `context` (JSON, nullable: what the rep chose when confirming a Market
  Discovery run, namely `product_ids`, `role_category_ids` and `market_fit_criteria`; it used to
  live only in the job payload), `created_at`

### IngestionRunCompany
Which companies a run is about. One company can belong to many runs, so membership is its own
table; `Company.source_ingestion_run_id` only names the first run that created it. `relation` is
`created` (this run found and created the company), `reused` (taken from the existing index) or
`matched` (found live but already existed). Unique on (`run_id`, `company_id`). Runs older than the
table were backfilled insert-only from the old sources (the company's source run and the run
summary's `company_ids`), and readers still honour those sources.

- `id`, `organization_id` (FK), `run_id` (FK), `company_id` (FK), `relation`, `created_at`

### Company
Deduplicated by domain (primary) within an organization.

- `id`, `organization_id` (FK), `name`, `domain`, `industry`, `employee_count_range`,
  `description`, `source_ingestion_run_id` (FK), `created_at`, `updated_at`
- `dismissed_at`, `dismissed_reason`, `dismissed_note` (all nullable): the "Not a fit" mark.
  `dismissed_reason` is one of a fixed list (`wrong_industry`, `wrong_size`, `wrong_location`,
  `not_a_real_company`, `already_a_customer`, `other`), shared with the frontend and checked by
  `governance_checks/test_not_a_fit_reasons_match.py`. `dismissed_at` set means dismissed.
- `discovery_evidence` (JSON, nullable): what Market Discovery saw when it proposed the company (the
  source snippet, the extraction model's own reasoning and the market that was asked for), kept so
  a later review can tell why the search got it wrong.

A dismissed company is hidden from lists by default (`GET /companies?dismissed=hide|include|only`),
left out of the discovery reuse index and out of every automatic job (auto pipeline, bulk
qualification, bulk scrape, contact verification, the Needs Review queue, follow-up reminders,
dashboard figures, run results). Finding it again in a later Market Discovery run does not revive
it (the run counts it as `skipped_dismissed`). Drafting and role classification for it are refused
until it is restored. Existing outreach is never touched. If a company has logged outreach or sent
drafts the server refuses to dismiss it (409) until the person confirms.

### Contact
A person at a Company. Deduplicated by (company_id, email) once an email is known.

- `id`, `organization_id` (FK), `company_id` (FK), `full_name`, `role_title`, `seniority`,
  `created_at`, `updated_at`

### ContactChannel
An email or phone number for a Contact, with provenance and (later) verification status.

- `id`, `contact_id` (FK), `channel_type` (`email` | `phone`), `value`,
  `verification_status` (`unverified` | `valid` | `invalid` | `unknown`, default `unverified`),
  `source` (which provider/scrape produced it), `created_at`

### EnrichmentRecord
Raw payload from a given source for a Company or Contact — kept for provenance/auditability and
to allow re-processing when a source/provider changes.

- `id`, `organization_id` (FK), `entity_type` (`company` | `contact`), `entity_id`,
  `source`, `raw_payload` (JSONB), `fetched_at`, `company_opportunity_id` (FK, nullable)

`company_opportunity_id` is set when a record was gathered for one business area of a company (for
example a search focused on that area); null means company-level evidence shared by every area.
Area evidence has its own `source` prefix (`opportunity:`), so the company-level signal lists never
include it.

### Recommendation
Internal sales-prep intelligence for a (Company, Contact) pair — what to pitch, why, how
(talking points). Read by the salesperson before they reach out; **not** customer-facing message
copy (that's a separate Reach Out concern).

- `id`, `organization_id` (FK), `company_id` (FK), `contact_id` (FK, nullable),
  `product_id` (FK), `pitch_summary`, `why_this_company`, `talking_points` (JSONB/text),
  `model_used`, `prompt_version` (nullable), `company_opportunity_id` (FK, nullable), `opportunity_assessment_id` (FK,
  nullable), `created_at`

A recommendation written for an opportunity records it and the assessment version it was grounded
in, and is unique per (opportunity, offering, assessment version), so reopening a page or a double
click cannot create a duplicate. Earlier recommendations have no opportunity and read as general.

### QualificationCriterion
An org-defined rule a company will be judged against (e.g. "minimum IT spend", "digital
transformation maturity") — user/org-configurable, not hardcoded (Phase A2.1). `is_disqualifying`
is explicit on the criterion itself rather than inferred from wording by a future judgment step:
if a company clearly fails an `is_disqualifying` criterion, that's an automatic not-qualified
verdict. `is_active` retires a criterion without deleting it or breaking judgment history that
references it. No judgment logic exists yet as of this phase — see Phase A2.2 in
[`docs/roadmap.md`](roadmap.md).

- `id`, `organization_id` (FK), `name`, `description`, `is_disqualifying`, `is_active`,
  `created_at`, `updated_at`

### QualificationResult
A point-in-time qualification judgment for a Company against the org's active criteria at that
moment (Phase A2.2). Append-only, same spirit as `Recommendation`: re-checking creates a new row
rather than overwriting, so history (including "was this qualified before, and is it still now")
is preserved. `overall_verdict` is computed deterministically in code from `criteria_results` —
never decided by the LLM. Only `is_disqualifying` criteria gate the overall verdict; the LLM's
only job is judging each individual criterion against the evidence. `criteria_results` is a
snapshot of each criterion **as it was when judged** (name, `is_disqualifying`), not a live
reference, so a later edit to a `QualificationCriterion` never rewrites past judgment history.

Each criterion verdict must now be evidence-backed (`qualification/evidence.py`): the model cites
an `evidence_ref` (a company field, or a numbered signal like `S2`) and an `evidence_quote` that
must appear verbatim in that cited source — a verdict whose quote doesn't actually check out is
downgraded to `could_not_determine` in code before it's persisted, never trusted as a bare
assertion. `priority_score`/`score_breakdown` (nullable — only qualified/undetermined companies
that reach the ranking step get one) hold the deterministic, auditable Priority Score
(`qualification/ranking.py`) used to pick the best-scoring companies for role-classification/
drafting, not just the first ones discovered.

`focus` (nullable) records the area a Quick Check was asked to judge fit around (for example a
technology or service line). It is empty for every other result, so a focused result is never
mistaken for a general one.

- `id`, `organization_id` (FK), `company_id` (FK), `overall_verdict`
  (`qualified` | `not_qualified` | `could_not_determine`), `criteria_results` (JSONB — per-entry
  `{criterion_id, criterion_name, is_disqualifying, verdict, reasoning, evidence_ref,
  evidence_quote}`), `priority_score` (float, nullable), `score_breakdown` (JSONB, nullable),
  `focus` (nullable), `model_used`, `prompt_version` (nullable), `created_at`

### QualificationCriterionResult (Phase 8a)
The same per-criterion judgments as `criteria_results`, one row each, so they can be counted and
filtered in SQL (the dashboard reads these). Written together with the JSON; the JSON column stays
for one release and is then dropped. `criterion_id` is a copied value, not a foreign key, because
criteria defined for a single search are never saved as rows.

- `id`, `organization_id` (FK), `qualification_result_id` (FK, cascade delete), `position` (order
  judged; unique per result), `criterion_id`, `criterion_name`, `is_disqualifying`, `scope`
  (`org` | `run`), `verdict` (`met` | `not_met` | `could_not_determine`), `status`
  (`PASS` | `FAIL` | `UNKNOWN`), `reasoning`, `evidence_ref`, `evidence_quote`, `confidence` (0-1,
  nullable), `source`, `url`, `created_at`

### RoleCategory
An org-defined function a `Contact` can be classified against (e.g. "Vendor / IT Procurement") —
user/org-configurable, not hardcoded, same reasoning as `QualificationCriterion` (Phase A3).
`is_primary_target` is no longer set or shown: which roles are targets is now chosen per
Market Discovery run (see `RoleRelevanceResult`), and the column is kept only so existing rows and
history stay valid. `framing_style` (`business` | `technical`,
Phase B) is likewise explicit — which register Phase B's draft generator writes in for a contact
matched to this category, never inferred by the LLM. `is_active` retires a category without
breaking classification history that references it.

- `id`, `organization_id` (FK), `name`, `description`, `is_primary_target`, `is_active`,
  `framing_style`, `created_at`, `updated_at`

### RoleRelevanceResult
A point-in-time role-relevance classification for a Contact against the org's active role
categories at that moment (Phase A3). Append-only, same spirit as `QualificationResult`:
re-classifying creates a new row rather than overwriting. `priority`
(`primary` | `secondary` | `not_relevant`) is computed deterministically in code, never decided by
the LLM, whose only job is matching a contact to the best-fitting category (or none). A run may
name target role categories: matches in those are `primary`, other matches `secondary`. When no
targets are named, every matched contact is `primary`, so no role is filtered out before a person
has looked at the contacts. Rows written before this change keep the priority they were given. `matched_category_name`/`is_primary_target`/
`matched_category_framing_style` are a snapshot **as judged**, not a live reference, so a later
edit to a `RoleCategory` never rewrites past classification history. See
[ADR 0006](decisions/0006-role-relevance-classification.md).

- `id`, `organization_id` (FK), `company_id` (FK, denormalized from `contact_id` for cheap
  per-company queries), `contact_id` (FK), `matched_category_id` (FK, nullable),
  `matched_category_name` (nullable), `is_primary_target`, `matched_category_framing_style`
  (nullable), `priority`, `reasoning`, `model_used`, `prompt_version` (nullable), `created_at`

### OutreachActivity
A logged outreach attempt or response (Phase C). Append-only, same spirit as
`QualificationResult`/`RoleRelevanceResult` — logging a new touch never overwrites a prior one.
Logging a `sent` activity auto-derives `Contact.status`/`next_follow_up_at`/`next_follow_up_channel`
via the send-window cadence rule (`outreach/cadence.py`); logging a `response_received` clears the
follow-up and marks the contact `responded`, leaving the next step to a human. `draft_id` (Phase B,
nullable) links back to the `Draft` that was approved and sent, when this activity was logged from
one rather than typed manually. See [ADR 0007](decisions/0007-tracker-cadence.md).

- `id`, `organization_id` (FK), `contact_id` (FK), `draft_id` (FK, nullable), `channel`
  (`email` | `linkedin`), `activity_type` (`sent` | `response_received`), `template_variant`
  (nullable, free-text — defaults from `Draft.draft_type` when logged from one), `notes`
  (nullable), `occurred_at`, `created_at`

### Draft
A generated first-touch/follow-up outreach message for one contact (Phase B) — customer-facing
message copy, unlike `Recommendation`'s internal sales-prep notes. Unlike every append-only
judgment log above, a `Draft` is a work-in-progress document a rep edits before sending: mutable
(`updated_at`), closer in spirit to `RoleCategory`/`Product` than to `QualificationResult`.
Regenerating does not create a new row automatically; editing mutates the same row in place.
`recommendation_id` (nullable) grounds the draft's proof-point content in an existing
`Recommendation` for the same (company, product) when one exists, rather than re-deriving
credibility content from scratch. `status` moves `draft` → `sent` (when logged via an
`OutreachActivity`) or `draft` → `discarded`. See
[ADR 0008](decisions/0008-outreach-draft-generation.md).

A rep may now give the auto-pipeline *more than one candidate* product at confirm time, but this
row's own `product_id` stays a single required FK regardless — it always records the one product
the draft generator actually chose to pitch for this specific company/contact, never a list.

- `id`, `organization_id` (FK), `company_id` (FK), `contact_id` (FK), `product_id` (FK),
  `recommendation_id` (FK, nullable), `company_opportunity_id` (FK, nullable), `draft_type` (`first_touch` | `follow_up` (the first
  follow-up) | `follow_up_2` | `follow_up_3`), `channel`
  (`email` — LinkedIn deferred), `subject` (nullable, email only), `body`, `status`
  (`draft` | `sent` | `discarded`), `model_used`, `prompt_version` (nullable),
  `grounding_flags` (JSON list, nullable), `created_at`, `updated_at`

`grounding_flags` holds what `draft/claims.py` found in the finished email: figures (percentages,
money, multipliers, counts of years or clients) and past-work wording ("case study", "our clients",
"we helped", "trusted by") that were not in what the draft was given (company description,
offering, recommendation, research signals, earlier emails), at most five. The app shows them as
"Check before sending". They warn and never block, are worked out when the draft is generated (not
after a person edits it), and are empty on drafts written before the check existed.

### CompanyOpportunity
A company seen through one business area, for example "cloud migration"; `area_key` `general` is the
company as a whole. It is the stable context that everything specific to an area hangs on, so two
areas for one company can never collide. Unique on (`organization_id`, `company_id`, `area_key`),
where the key is a normalised slug of the label, so the same area typed two ways is one row.
`origin` is `quick_check`, `market_discovery`, `suggested` or `manual`; `status` is `suggested`
(proposed from evidence, nothing deep researched yet), `active` or `archived`. `industry_context`
snapshots the company's industry when the opportunity was created. A company in several Market
Discovery runs still has one opportunity per area; run membership lives in `ingestion_run_companies`.

- `id`, `organization_id` (FK), `company_id` (FK), `area_key`, `area_label`, `origin`, `status`,
  `industry_context`, `created_by_run_id` (FK, nullable), `suggestion_reason`, `research_log`
  (JSON, nullable), `created_at`, `updated_at`

`research_log` records what each research collector (`news`, `hiring`, `web`) did last time: when,
what it searched, how much it found, any error and, for hiring, the number of open roles and the
count of matching postings over time (a trend needs two counts). It decides what is still fresh and
is the source of the plain "searched, found nothing" statements on an assessment.

### OpportunityAssessment
What the evidence says about a company in one area at one point in time. Append-only and versioned
per opportunity (unique on `company_opportunity_id`, `version`). Each finding (kind: initiative,
hiring, news, partnership or technology) cites its evidence by stable identity: the record id (or
company field), source address, fetch time, a hash of the text it was found in and the exact quote,
which must appear verbatim in that text or the finding is dropped (`dropped_count`). The verdict
(`supported`, `emerging`, `weak` or `insufficient_evidence`) is computed in code from the verified
findings (`opportunity/sufficiency.py`), never by the model: a company's own description can never
lift it above `weak`, and a `hiring` finding needs an actual job posting. `not_found` lists what was
looked for and not found. `evidence_set_hash` fingerprints everything the model was shown and, with
`prompt_version`, is the cache key: unchanged evidence is not judged again.

- `id`, `organization_id` (FK), `company_opportunity_id` (FK), `version`, `verdict`, `summary`,
  `findings` (JSON), `not_found` (JSON), `dropped_count`, `evidence_count`, `evidence_set_hash`,
  `prompt_version`, `model_used`, `created_at`

### OpportunityOfferingMatch
How well one offering fits a company in one area, at one point in time. Append-only. The model
explains the fit and cites evidence (each citation is verified); the **band** (`strong`,
`potential`, `weak`, `insufficient_evidence`) and the 0 to 100 `score` are computed in code from
`factors`: the number of distinct pieces of verified evidence, whether the offering belongs to the
area (its area tags share a word with it), how many of its profile keywords the evidence uses, and
the opportunity's verdict. `strong` needs at least two pieces of verified evidence, the offering
belonging to the area and an opportunity that is supported or emerging. A match is reused while the
latest assessment, the offering's `profile_hash`, the evidence fingerprint and the prompt version
are unchanged. `needs_review` is set when a citation failed verification or a "possible" fit rests
on alignment alone.

- `id`, `organization_id` (FK), `company_opportunity_id` (FK), `product_id` (FK), `assessment_id`
  (FK, nullable), `band`, `score`, `factors` (JSON), `reasoning`, `evidence` (JSON, verified
  citations), `needs_review`, `profile_hash`, `evidence_set_hash`, `prompt_version`, `model_used`,
  `created_at`

### ContactOpportunityRelevance
What part a contact plays for an opportunity, optionally for one offering. Append-only. A model's
judgment and a person's override are different rows told apart by `source`: on read, the latest
human row wins and the model's row stays visible beneath it, and a human row with role `revert`
withdraws an earlier override. The model sees only the title, seniority, company context, area and
the offering's buyer profile, labelled `C1`, `C2`..., never a name or id. Roles are `decision_maker`,
`influencer`, `user` and `not_relevant`; low-confidence results are flagged `needs_review`. A contact
is judged again only when the title or seniority (`contact_hash`), the assessment, the offering
profile or the prompt version changed.

- `id`, `organization_id` (FK), `company_opportunity_id` (FK), `contact_id` (FK), `product_id` (FK,
  nullable), `source` (`model` | `human`), `role`, `function`, `reasoning`, `confidence`,
  `needs_review`, `note`, `assessment_id` (FK, nullable), `profile_hash`, `contact_hash`,
  `prompt_version`, `model_used`, `created_at`

### ApiUsage
One row per call, or retry attempt, to a paid or rate-limited service: a language model (Gemini,
Groq), a web search query (Serper) or a context.dev request. Append-only operational log written
in its own short session, so a rolled-back job keeps its cost record. The company, run, job and
opportunity ids are plain columns with no foreign keys on purpose, so the log survives a test-data
wipe. `est_cost_usd` is an estimate from published prices (`usage/pricing.py`), not a bill; Groq
calls record tokens but no cost because no price was found. Read it with
`backend/scripts/usage_report.py`.

- `id`, `created_at`, `organization_id`, `job_id`, `run_id`, `company_id`, `opportunity_id`
  (all nullable), `provider` (`gemini` | `groq` | `serper` | `contextdev`), `kind` (`llm` |
  `search` | `credits`), `model`, `task` (the job type, `api:<route>` for a call made inside a web
  request, or `unspecified`), `status` (`ok` | `error`), `tokens_in`, `tokens_out`, `units`
  (queries or credits), `latency_ms`, `est_cost_usd`
- `cached_tokens`, `thinking_tokens` (nullable): read from the Gemini reply. Cached tokens stay
  inside `tokens_in` and thinking tokens stay inside `tokens_out`, so cost estimates do not move.
  They show whether Gemini's automatic caching is working. Rows from before are empty.
- `error` (nullable): why a failed call failed, the provider's own message, shortened, with
  key-like text removed. `scripts/usage_report.py` lists failed calls by reason.

### CompanySnapshot (table `company_snapshots`)
The cached answer of a Quick Look (the app's "Quick Check"): what a company does, which of our
offerings it might fit, the sources, and a yes / maybe / no call. One row per organization and
domain (unique `uq_snapshots_org_domain`). It is **not** a company: nothing reaches the Companies
list until a person saves it (`POST /quick-look/save`). The model proposes offerings, code verifies
that each quoted source text exists and computes the call. `offerings_hash` fingerprints the
offerings it was judged against, so changing Our Offerings makes the snapshot stale.

- `id`, `organization_id` (FK), `domain`, `name`, `summary` (JSON), `sources` (JSON list),
  `offerings_hash`, `model_used`, `prompt_version`, `created_at`

### ReviewDecision (table `review_decisions`)
Append-only record of what a person decided about something the system flagged (control G4 in
[`ai-governance.md`](ai-governance.md)). Written by `modules/review/` when a flagged company or
contact is confirmed, a contact is deleted, or a company is marked "not a fit" or restored.
`snapshot` is what the person saw at the time (never names or emails); `flag_reason` is the
system's own reason for flagging. This is the data a future Market Discovery judge and the
accuracy evals will learn from.

- `id`, `organization_id`, `subject_type` (`company` | `contact`), `subject_id`, `company_id`
  (nullable), `decision` (`confirmed` | `deleted` | `not_a_fit` | `restored`), `was_flagged`,
  `flag_reason` (nullable), `reason_code` (nullable, the "not a fit" reasons above), `note`
  (nullable, typed by a person, up to 500 characters), `snapshot` (JSON, nullable), `created_at`

Ids here are plain columns with no foreign keys, like `ApiUsage`, so the log outlives a test-data
wipe.

### AI-written rows: model and prompt version
Every table a model writes to records `model_used` and `prompt_version` (control G9, enforced by
`governance_checks/test_ai_rows_record_model_and_prompt.py`): drafts, qualification results, role
relevance results, recommendations, opportunity assessments, offering matches, contact relevance,
company snapshots and offering proposals. Rows written before 2026-11-04 have them empty on
purpose, and offering proposals made from a 404 check (removals) stay empty because no model wrote
them.

### CreditTransaction
Ledger entry for a credit-consuming action. Balance is always derived from summing the ledger —
never a mutable counter — so usage is auditable.

- `id`, `organization_id` (FK), `action_type` (`enrichment` | `verification` | `ai_call`),
  `amount`, `related_entity_type`, `related_entity_id`, `created_at`

### Job
Background work unit backing the simplified job queue (see `docs/architecture.md`).

- `id`, `organization_id` (FK), `job_type`, `status` (`pending` | `running` | `done` | `failed`),
  `payload` (JSONB), `result` (JSONB, nullable), `error` (text, nullable), `created_at`,
  `started_at`, `finished_at`

## Relationships

```
Organization 1──* User
Organization 1──* Product
Organization 1──* OfferingProposal
Organization 1──* OfferingPage
Product 1──* OfferingProposal        (nullable — a new offering has no product yet)
Organization 1──* IngestionRun
Company 1──* CompanyOpportunity
CompanyOpportunity 1──* OpportunityAssessment
CompanyOpportunity 1──* EnrichmentRecord   (nullable: area evidence; null = company-level)
IngestionRun 1──* IngestionRunCompany
Company 1──* IngestionRunCompany     (a company can belong to many runs)
Organization 1──* Company
IngestionRun 1──* Company            (companies sourced by a given ingestion run)
Company 1──* Contact
Contact 1──* ContactChannel
Company/Contact 1──* EnrichmentRecord (polymorphic via entity_type/entity_id)
Company 1──* Recommendation
Product 1──* Recommendation
Organization 1──* QualificationCriterion
Company 1──* QualificationResult
Organization 1──* RoleCategory
Contact 1──* RoleRelevanceResult
Company 1──* RoleRelevanceResult
Contact 1──* OutreachActivity
Draft 1──* OutreachActivity          (nullable — only when logged from an approved draft)
Company 1──* Draft
Contact 1──* Draft
Product 1──* Draft
Recommendation 1──* Draft            (nullable — grounding, not required)
Organization 1──* CreditTransaction
Organization 1──* Job
Organization 1──* CompanySnapshot    (one per domain; not a Company until saved)
ReviewDecision *──1 Company/Contact  (by id only, no foreign key; append-only log)
ApiUsage       *──1 Job/Run/Company  (by id only, no foreign key; append-only log)
```

This is deliberately not yet a full ER diagram with cardinalities/constraints — that will firm
up as Phase 1 migrations are written. This document should be kept current as the schema
evolves.

## Documents (Phase 8b)
The knowledge base: decks, PDFs, Word, Markdown and text files about what we sell. **No original file
is kept.** An upload sits in `document_uploads` only until the background job has read it (a failed
read is held for 24 hours so it can be run again); what remains is the text the file said.

- `documents`: the library entry (`name`, optional `uploaded_by`, `organization_id`). The offerings it
  is about are in `document_offerings` (none = general, like a company deck).
- `document_versions`: one per upload. A changed deck becomes a new version; the old one keeps being
  used until the new one is read, then it is archived (`is_current` false) but kept. At most one
  current version per document (partial unique index). `status` is `queued` | `processing` | `ready`
  | `failed`. `content_hash` (SHA-256) stops the same bytes being stored twice.
- `document_pages`: everything a file said on one page, slide or section, in reading order.
- `document_chunks`: the passages search finds (about 1000 characters, slide- and page-aware, split
  at sentences, tables split by rows with the header repeated), each with its locator ("Slide 7") and
  heading path for citation. `tsv` is a full-text column the database keeps itself; `embedding`
  (`vector(768)`, Gemini `gemini-embedding-001`, unit length) and `embedding_model` are filled by a
  separate background job (`embed_document`) after the file is read, so a spent quota never fails a
  read. An HNSW cosine index serves nearest-neighbour search. Search merges meaning and words by
  reciprocal rank fusion over the current version of each document.
- `document_assets`: pictures, charts, unreadable tables and scanned pages that a model described
  (Gemini vision, optional), or that were skipped or failed. These words are written by a model, so
  each row records `provider`, `model_used`, `prompt_version`, tokens and estimated cost (G9).
- `document_ingestion_events`: what happened while a version was read, with timings and errors.
- `document_audit`: one line per upload, new version, re-read, rename and delete, with the document's name at the time. Not tied to the document by a foreign key, so it survives a delete (the ingestion events above do not). `user_id` is filled once login exists.
