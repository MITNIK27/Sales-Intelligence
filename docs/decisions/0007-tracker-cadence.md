# ADR 0007: Tracker & Cadence Mechanics — Append-Only Activity Log, Derived Tracker State

**Status:** accepted
**Date:** 2026-09-11

## Context

Phase C automates Abhas's manual tracker — the thing he explicitly said burns him out to maintain
by hand ("half of your enthusiasm goes down"). Before this, the app only had the single-contact
manual-entry version of tracking (`Contact.status`/`next_follow_up_at`/`next_follow_up_channel`,
set by hand via `PATCH /contacts/{id}/tracking`). The scope here is specifically: auto-updating
that state after a send/response, send-window scheduling, proactive reminders, and A/B data
capture — not outreach draft generation itself (Phase B, separate and still not started).

## Decisions

1. **`OutreachActivity` is append-only** (`TimestampMixin` only, no `updated_at`, no unique
   constraint) — the same pattern as `QualificationResult`/`RoleRelevanceResult`. Logging a new
   send or response never edits a prior entry; it's an event log, and an event that already
   happened shouldn't become editable history. `Contact.status`/`next_follow_up_at`/
   `next_follow_up_channel` are the *derived, current* state, recomputed from the latest event by
   `outreach/service.py::log_outreach_activity` — not themselves an edit to the append-only log.
   Manual override via the pre-existing `PATCH /contacts/{id}/tracking` stays available for
   anything the auto-derivation doesn't cover, mirroring the append-only-plus-manual-override
   layering already decided for role-relevance (ADR 0006).

2. **No job queue for this.** The job-queue pattern in this codebase (Job model + standalone
   worker) exists specifically for slow, network/LLM-bound work — scraping, Gemini calls. Logging
   an activity and computing a send-window slot is fast, synchronous, in-process date math with no
   external I/O, so it's a normal request/response endpoint, exactly like the existing tracking
   PATCH. Routing it through the job queue would add asynchronous complexity (polling, job status)
   for work that completes in milliseconds — structure for its own sake, not precision.

3. **Send-window math is a pure function**, isolated from any DB/session access
   (`outreach/cadence.py::next_send_window_slot`) — this is the piece of logic where correctness
   matters most (it directly encodes Abhas's stated rule: Mon-Wed always, Thursday only if urgent,
   never Friday/weekend, ~11:00 recipient-local), so it needed to be exhaustively unit-testable
   across weekday boundaries without spinning up a database.

4. **Per-contact timezone, not one org-wide default.** "Recipient-local time" only means something
   with a real timezone per contact. `Contact.timezone` (nullable IANA string) was added rather
   than approximating with a single hardcoded zone for every contact — most contacts won't have one
   set initially (falls back to `settings.default_timezone`), but the field exists so this is
   opt-in precision that improves as data is filled in, not a permanent simplification.

5. **A responded contact gets its own status** (`TRACKING_STATUS_RESPONDED`), distinct from
   `follow_up_scheduled`. Logging a response clears `next_follow_up_at`/`next_follow_up_channel`
   rather than auto-scheduling a next touch — there's no Phase B yet to decide what a reply should
   trigger, so this is deliberately a human-in-the-loop handoff, not an attempt to automate a step
   the system doesn't have the context to make yet.

6. **Channel vocabulary reconciled to `email | linkedin` everywhere.** Before this phase, three
   separate and inconsistent channel enums existed in the codebase (`Contact.next_follow_up_channel`
   as `email|phone|whatsapp`, the documented-but-unbuilt `OutreachActivity.channel` as
   `email|whatsapp|call`, and `ContactChannel.channel_type` as `email|phone` — a different concept,
   a contact's own reachable addresses, left untouched). Abhas was explicit in the meeting: email
   and LinkedIn only, no cold calling for international contacts ("they don't appreciate cold
   call... he'll block me and blacklist our company"). Both channel-of-next-touch fields now share
   the single correct `email | linkedin` vocabulary from day one, rather than shipping the
   documented mismatch and fixing it later.

7. **A/B variant capture now, reporting later.** `OutreachActivity.template_variant` is a free-text
   field captured on every logged send so data isn't lost once Phase B exists to generate real,
   named variants. The aggregate stats endpoint/UI was explicitly deferred — with no template
   entity yet, building a report against a single hardcoded variant would be speculative surface
   area, not a feature grounded in real use.

## Consequences

- A rep still has to manually log that an email/LinkedIn message was sent or a reply came in —
  Phase C automates what happens *after* that's logged (tracker state, next date), not the sending
  itself. Automating the send is Phase B's job.
- Reminder surfacing today is a due-count badge on the sidebar plus the existing `/follow-ups`
  list — genuinely proactive push notifications (email/Slack) are out of scope for this phase.
- Because A/B reporting is deferred, `template_variant` data will accumulate with no way to view
  it in aggregate until Phase B ships — an accepted tradeoff to avoid building a report with no
  real variants to compare yet.
