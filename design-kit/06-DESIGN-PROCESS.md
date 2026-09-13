# Design Process — idea to shipped InfoBeans app

The method behind the standards. Each stage produces one markdown artifact that the next stage
builds from — **the artifact is the contract**. Never re-derive facts a previous artifact settled.

You can enter at any stage by supplying that stage's input. For a small app, stages 1–2 can be a
single short pass; never skip stage 3's states or stage 4's accessibility gate.

---

## Stage 1 — Discovery → `brief.md`

Turn a starting point (a live app, a Figma file, a requirements doc, a wireframe, or just an idea)
into a framed problem.

**Do:** inspect the real thing — don't describe a screen you haven't opened. For an existing app,
catalogue every screen: purpose, key tasks, states seen, friction. Reconcile conflicting sources
rather than silently picking one.

**Produce:** problem & opportunity · users & context · jobs to be done · current-experience summary
· scope (in / out / deferred) · brand & experience direction · constraints vs assumptions ·
success metrics · risks · open questions (with owners).

**Rules:** anything unverified is marked `Unknown — requires review`, never invented. No fabricated
metrics, counts, or brand values.

---

## Stage 2 — Strategy → `strategy.md`

Decide who you're designing for, what to solve first, and how the product is structured.

**Produce:**
- **Personas** — only real observed roles, each tagged `validated` or `assumption`.
- **Current-state journey maps** — stages → actions → touch-points → pain (with severity) →
  opportunity. Each pain cites its evidence.
- **Target IA** — the navigation model. Group by ownership and role, not by feature list. Name the
  rationale for each change.
- **Prioritised backlog** — `problem · job/persona · evidence · impact · effort · P0/P1/P2`.
  No priority without evidence. **P0 = what stage 3 builds.**
- **Design principles** — 3–6 that arbitrate later decisions, each ruling something in and out.
- **Success metrics** — measurable, tied to backlog items.

---

## Stage 3 — Design & build → the app

Build the P0 screens as a real Vite + React + TS + shadcn app (`03-SHADCN-SETUP.md`), themed with
`02-THEME.md`, using the patterns in `04-COMPONENT-PATTERNS.md`.

**Per screen:** the user flow → layout structure → hi-fi implementation → **all four states**
(default, empty, loading, error) → role variants.

**Write a short spec per screen** (purpose & job · layout · components · tokens bound · states ·
interactions · responsive · accessibility · edge cases · open questions). The spec is what
developers and agents build from.

**Never:** lorem where a real label is known · a hardcoded hex · a table that overflows the page ·
a wrapped column header · a blank empty state.

---

## Stage 4 — Validation → `validation.md`

Run against the *running* app, not a description.

1. **Heuristic pass** on every P0 screen (Nielsen's 10), each issue with a severity 0–4.
2. **WCAG 2.1 AA audit** — measure real contrast ratios; check keyboard, focus visibility,
   icon-button labels, table semantics, reduced-motion. **AA failures block release** (the one
   standing exception is the documented crimson pairing).
3. **Usability** — task success per P0 job. With users if possible; otherwise an expert
   walkthrough, explicitly labelled as not user-tested.
4. **Regression** — verify each original problem the redesign promised to fix is actually gone.

**Produce:** verdict (ship / ship-with-fixes / iterate) · ranked findings, each with evidence,
severity, and a proposed fix · what loops back to stage 3 · what's cleared to ship.

---

## Stage 5 — Production → `handoff.md`

Harden the same codebase — don't rebuild.

**Gate:** every stage-4 blocker fixed and re-checked first.

**Then:** real routing (role-gated) · typed data layer with loading/error/empty wired to real async
· auth + role resolution (never handle credentials in the client — use the org's provider) ·
forms with schema validation · tests (component + one e2e per P0 job) + accessibility checks in CI
· clean `build` / `lint` / `test`.

**Handoff covers:** architecture · data contracts · environment vars · run/build/deploy ·
component & token reference · accessibility notes · open items with owners.

---

## Stage 6 — Launch & iterate

Measure the shipped product against the stage-2 metrics, capture real baselines, and open the
next cycle's backlog. Re-run stage 4 after any significant change.

---

## Quick checklist before you call a screen done

- [ ] Reads as InfoBeans: cream ground, white cards, Lexend 700 headings, 0px radius
- [ ] Every colour comes from a token — `grep` finds no hex in your components
- [ ] Default / empty / loading / error all designed
- [ ] Data table has pagination + page-size selector
- [ ] Footer shows copyright + version
- [ ] Contrast measured; keyboard reachable; icon buttons labelled
- [ ] Irreversible actions have a confirm or an undo
- [ ] Spacing only from `[4…80]`; content capped at 1320px
