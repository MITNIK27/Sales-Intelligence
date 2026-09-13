# Data Model

## Entities

### Organization (tenant)
The owning org. Only one exists today (internal use), but every other entity is scoped to an
`organization_id` from the start so multi-tenancy doesn't require a later migration.

- `id`, `name`, `created_at`

### User
- `id`, `organization_id` (FK), `email`, `hashed_password`, `role`, `created_at`

### Product
The org's own catalog of products/services — needed so the AI recommendation layer has
something concrete to recommend pitching.

- `id`, `organization_id` (FK), `name`, `description`, `created_at`

### IngestionRun (job)
One CSV upload or one Market Discovery request. Tracks the batch through the pipeline.

- `id`, `organization_id` (FK), `source_type` (`csv` | `market_discovery`), `status`,
  `created_by_user_id`, `created_at`

### Company
Deduplicated by domain (primary) within an organization.

- `id`, `organization_id` (FK), `name`, `domain`, `industry`, `employee_count_range`,
  `description`, `source_ingestion_run_id` (FK), `created_at`, `updated_at`

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
  `source`, `raw_payload` (JSONB), `fetched_at`

### Recommendation
Internal sales-prep intelligence for a (Company, Contact) pair — what to pitch, why, how
(talking points). Read by the salesperson before they reach out; **not** customer-facing message
copy (that's a separate Reach Out concern).

- `id`, `organization_id` (FK), `company_id` (FK), `contact_id` (FK, nullable),
  `product_id` (FK), `pitch_summary`, `why_this_company`, `talking_points` (JSONB/text),
  `model_used`, `created_at`

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

- `id`, `organization_id` (FK), `company_id` (FK), `overall_verdict`
  (`qualified` | `not_qualified` | `could_not_determine`), `criteria_results` (JSONB — per-entry
  `{criterion_id, criterion_name, is_disqualifying, verdict, reasoning}`), `model_used`,
  `created_at`

### RoleCategory
An org-defined function a `Contact` can be classified against (e.g. "Vendor / IT Procurement") —
user/org-configurable, not hardcoded, same reasoning as `QualificationCriterion` (Phase A3).
`is_primary_target` is explicit on the category itself: contacts matched to a primary-target
category are the ones surfaced first for outreach. `framing_style` (`business` | `technical`,
Phase B) is likewise explicit — which register Phase B's draft generator writes in for a contact
matched to this category, never inferred by the LLM. `is_active` retires a category without
breaking classification history that references it.

- `id`, `organization_id` (FK), `name`, `description`, `is_primary_target`, `is_active`,
  `framing_style`, `created_at`, `updated_at`

### RoleRelevanceResult
A point-in-time role-relevance classification for a Contact against the org's active role
categories at that moment (Phase A3). Append-only, same spirit as `QualificationResult`:
re-classifying creates a new row rather than overwriting. `priority`
(`primary` | `secondary` | `not_relevant`) is computed deterministically in code from the matched
category's `is_primary_target` flag — never decided by the LLM, whose only job is matching a
contact to the best-fitting category (or none). `matched_category_name`/`is_primary_target`/
`matched_category_framing_style` are a snapshot **as judged**, not a live reference, so a later
edit to a `RoleCategory` never rewrites past classification history. See
[ADR 0006](decisions/0006-role-relevance-classification.md).

- `id`, `organization_id` (FK), `company_id` (FK, denormalized from `contact_id` for cheap
  per-company queries), `contact_id` (FK), `matched_category_id` (FK, nullable),
  `matched_category_name` (nullable), `is_primary_target`, `matched_category_framing_style`
  (nullable), `priority`, `reasoning`, `model_used`, `created_at`

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

- `id`, `organization_id` (FK), `company_id` (FK), `contact_id` (FK), `product_id` (FK),
  `recommendation_id` (FK, nullable), `draft_type` (`first_touch` | `follow_up`), `channel`
  (`email` — LinkedIn deferred), `subject` (nullable, email only), `body`, `status`
  (`draft` | `sent` | `discarded`), `model_used`, `created_at`, `updated_at`

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
Organization 1──* IngestionRun
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
```

This is deliberately not yet a full ER diagram with cardinalities/constraints — that will firm
up as Phase 1 migrations are written. This document should be kept current as the schema
evolves.
