# Project Overview

_Last updated: 2026-11-16._

## What it is

Sales Intelligence is an internal InfoBeans tool that does the groundwork of B2B prospecting for a
salesperson. Given a target market or a single company, it finds and researches companies, judges
whether each is worth pursuing, finds the right people to contact, works out what to pitch from
InfoBeans' own offerings, and writes the first email, with the evidence for each step in front of
the rep. The rep reviews and sends; the tool does not send anything itself.

It grew out of one sales rep's real routine (a spreadsheet of companies, contacts, channels and
follow-up dates, and cold emails written by hand to a strict formula). It is being proven with
InfoBeans' sales team first; the data model is multi-tenant so it could later serve other teams.

## Who uses it, and for what

| Person | Typical use |
|---|---|
| Sales rep | Describe a market, review what the system found, confirm contacts, edit and send drafts, work the follow-up list |
| Manager | Hand a rep a company name to research; read the leadership dashboard |
| Customer success | Same research and drafting for existing accounts (a use case still being designed, see below) |
| Whoever maintains the catalog | Approve updates to Our Offerings, keep criteria and role categories current |

## How it is used

1. **Set up once.** Our Offerings (what InfoBeans sells) and Role Categories (which functions matter);
   criteria are optional and typed per search or per company. Offerings fill themselves
   from the website; a person approves them.
2. **Find companies.** Describe a market in plain words in **Market Discovery** (the system shows
   how it understood it and the rep corrects it), or **upload a CSV** of known prospects. Optional
   per-run choices: offerings to pitch, target roles to focus on, extra hard requirements.
3. **Let the pipeline run.** One background job discovers companies, enriches them, judges each
   against the criteria with cited evidence, ranks them by Priority Score, and classifies contacts
   by role.
4. **Review.** The run worklist shows what was found. **Verify Contacts** lists contacts that need
   a human look; the rep confirms or discards them. Drafts are written only for confirmed contacts.
5. **Reach out.** **Drafts** are written for the email type (first touch or follow-up 1 to 3) and
   for the offering (product or service). The rep edits, sends it themselves, and logs it as sent.
   **Follow-ups** then lists who is due, scheduled to sensible send windows.
6. **One-off research.** **Quick Check**: type a company name or website, optionally a focus area,
   and get a short answer with evidence, the offerings that might fit and a yes, maybe or no call in
   a minute or two. It creates no company until the rep saves it.
7. **Say no, and have it stick.** **Not a fit** takes a company out, with a reason from a short list,
   singly or in bulk. It is left out of every automatic step, is not brought back by later searches,
   and can be restored with Undo.

## What each screen does

- **Dashboard**: setup checklist and a read-only view of pipeline health and spend.
- **Market Discovery**: plain-language search; a live run screen that names the company being
  worked on and keeps a short trail of real events; a finish summary (found, fit, people sorted,
  ready, and the next step); "Ready for you" cards with logo, score and why it fits, opening full
  details in a dialog; and a highlighted list of companies that were not shown, each with the
  reason.
- **Companies**: every company, newest discovery first, with its pipeline status (discovered,
  enriched, qualified, roles classified, drafted), signals, contacts and drafts; an Active and "Not
  a fit" toggle. The company page also holds the **Brief**: pick an industry, a business area and
  an offering, see a map from evidence to engagement (verified, inferred and unsupported links
  drawn differently, gaps shown), and use **AI Recommended Areas** chips suggested from the
  evidence on file.
- **Verify Contacts**: bulk confirm or discard, with the offerings to pitch chosen from a compact
  picker.
- **Outreach**: Drafts (review, edit, log as sent) and Follow-ups (the due list) in one place.
- **Our Offerings**: Services and Products tabs, a "Check for updates" button plus an automatic
  weekly check, a review list for what was found, and "What was checked" showing every page looked
  at and why something may be missing.
- **Role Categories**: the rules the system judges roles against.
- **Upload CSV**, **Quick Check**: the two other ways in.

## How it decides, and why you can trust it

- Every qualification verdict cites a source and a verbatim quote that must appear in it;
  otherwise it becomes "could not determine".
- Pass or fail, priority and ranking are computed by code from those cited judgments, not decided
  by the model.
- The website import writes proposals only; a person approves before anything goes live.
- Descriptions are checked against the page they came from, and doubtful wording is flagged.
- Uncertain matches are flagged for review instead of silently trusted.
- Drafts may cite only verified facts and never invent a case study. The finished email is also
  checked in code: figures and past-work wording that were not in what the draft was given show up
  as a "Check before sending" note (a warning, not a block, and a heuristic).
- Web text is fenced in every prompt and treated as data, never instructions; every AI-written row
  records which model and prompt version wrote it; prompt changes need an eval report. See
  [`ai-governance.md`](ai-governance.md).
- A person's "not a fit" and confirm decisions are recorded with what they saw, so they can be
  learned from later.

## Current limits

- Contact details are found but not verified (no email or phone validity check yet).
- Sending is manual; there is no Gmail integration.
- No sign-in or access control yet, so it runs on a trusted network only.
- Free-tier limits cap how many companies are drafted per run.
- Most language tasks still use Gemini; Groq is used by the offerings importer.
- Reporting on which email wording works best is not built, although the data is captured.
- The eval set is small (37 cases, nine tasks) and accuracy against real labelled companies is not
  measured yet; five tasks are waiting for a first report.
- CI effectively runs only the governance checks, because the unit and frontend tests are
  git-ignored. Hiring coverage in opportunity research is partial (many companies use their own
  career sites).
- Quick Check's page and nav label say "Quick Check"; the code, API and module call it Quick Look.

## Where the product is heading

The next phase is making the tool fit the daily routine of a sales or customer-success rep with
the least effort: fewer steps between "I have a company or a list" and "I sent a good email", and
clear starting points for the two roles. It will be planned from how each role actually works, not
from the feature list. See [`roadmap.md`](roadmap.md) for planned items and
[`decisions/`](decisions/) for the reasoning behind existing choices.
