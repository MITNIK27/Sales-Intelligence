# ADR 0017: Sign-in with Google through Firebase, invite-only access, and roles

**Status:** accepted
**Date:** 2026-11-24

## Context

Until Phase 9 anyone who could reach the app could use all of it: the API checked nothing and
every action ran as one fixed organisation. The app holds client data, people's names and emails,
and spends AI and search credits, so it could not be deployed as it was. ADR 0016 had already
decided that users live in our Postgres and that Firebase Authentication would handle sign-in.

Constraints:
- InfoBeans mail runs on Google Workspace, so a Google account is what every colleague already has.
- No passwords of our own to store, reset or leak.
- The team wanted control over who gets in, and a simple way to ask for access.
- Roles should limit a few sensitive things now, and be easy to tighten later without touching
  routes or screens.

## Decision

1. **Firebase proves who someone is; our database decides what they may do.** The browser signs in
   with Google through Firebase and sends the Firebase ID token on every request. The API checks it
   against Google's published certificates with `google-auth` (signature, audience, issuer, expiry),
   which needs only the project ID: no service-account key, so no secret to keep. Code also
   requires a verified email, Google as the sign-in provider, and an allowed domain
   (`AUTH_ALLOWED_DOMAINS`, default `infobeans.com`). The consent screen is set to Internal, so
   only InfoBeans Workspace accounts can complete Google sign-in at all.
2. **Invite only.** An admin or manager gives access by email and role, which creates a `users` row
   without a Firebase id; the first sign-in with that Google account links it. The app sends no
   email: the person is told by whoever added them. Someone who signs in without an invitation sees
   the app frame (Dashboard only) with a Request access card; requests (one per person per day)
   wait on User Management with a count badge. Emailing admins about a request is deferred until a
   mailbox is approved; `auth/service.py::notify_admins` is the one place it will go.
3. **The first admin** comes from `AUTH_BOOTSTRAP_ADMINS`: an address on that list becomes admin on
   its first sign-in. After that, roles live only in the database.
4. **Every API route requires a signed-in, active person**, attached once per router in
   `main.py`. The only exceptions are `/health` and the two `/auth` endpoints for people without
   access. `governance_checks/test_routes_require_sign_in.py` calls every endpoint without signing
   in and fails if one answers anything but 401, so a new router cannot be left open.
5. **Roles in one table** (`auth/permissions.py`): admin, manager, rep. Routes ask
   `require(Action.X)`; the browser gets the same list from `/auth/me` and hides what a role cannot
   use. Agreed for now: reps are kept out of User Management and costs; everything else is open to
   all roles but still routed through the table, so narrowing a row later is a one-line change.
   Managers manage people but cannot make, change or deactivate admins; nobody changes their own
   role or deactivates themselves; the last active admin stays.
6. **People are deactivated, never deleted**, so what they did stays attributed to them; only an
   invitation nobody has used can be removed. A deactivated person is refused on their next
   request, without waiting for their token to expire.
7. **Who did what.** The sign-in check puts the person's id in the request context
   (`usage/context.py`), which fills `documents.uploaded_by`, `document_audit.user_id`,
   `review_decisions.user_id`, `ingestion_runs.created_by_user_id`, `jobs.created_by` and
   `api_usage.user_id`. The worker runs each job as the person who queued it, so background work
   and its AI cost are attributed too.
8. **Still one organisation.** Users join the existing organisation and routers keep the fixed
   organisation id; a user of any other organisation is refused. Real separation between
   organisations is a later phase.

Alternatives considered: our own passwords (rejected: more to secure, and everyone already has a
Google account); Microsoft sign-in (InfoBeans mail is on Google); `firebase-admin` (needs a
service-account key; token checks need only public certificates); any InfoBeans account getting in
automatically (rejected in favour of invitations while the app holds client data and spends
credits).

## Consequences

- Easier: one click to sign in, no passwords, access managed in the app, and every action and cost
  traceable to a person.
- Harder: every new router must be mounted with the sign-in check (the governance check enforces
  it); local development needs the Firebase web settings in `frontend/.env.local` and
  `FIREBASE_PROJECT_ID` in `backend/.env`.
- Google outages: certificates are cached for as long as Google allows and the last good set is
  reused if a refresh fails, but a cold start during an outage cannot check tokens.
- **Gmail later:** signing in with Google does not give lasting access to a mailbox. Sending from
  the app will need its own Google consent with offline access, its refresh tokens stored
  encrypted (a `mailbox_connections` table), and its own ADR.
- Revisit: email to admins once a mailbox is approved; restricting the Firebase web key to the
  deployed domain; per-person visibility (if reps should see only their own work); separation
  between organisations before any other company uses the app.
