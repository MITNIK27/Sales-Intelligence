# InfoBeans Brand Standards — core values for every InfoBeans-branded app

**These are inherited automatically. Do not ask the user to restate them.** Every stage of the
product-design collection applies this file: Discovery captures brand inputs against it, Design
builds to it, Testing gates on it, Production ships it.

Precedence when sources disagree: **the user's explicit instruction → this file → the brand doc
(`DESIGN-infobeans-ai.md`) → the Figma design system.** Deviations are recorded in §8.

---

## 1. Non-negotiable core values

1. **WCAG 2.1 AA is a hard gate.** Contrast, keyboard, focus, labels. Accessibility failures
   **block release** — not "best effort". Enforced in Stage 4 and in CI.
   *One standing exception exists: the brand crimson pairing in §3. It is the only one.*
2. **Every state is designed.** Default, empty, loading, and error on every screen. Never a blank
   page or a bare spinner.
3. **Tokens only — never raw hex.** All UI binds to semantic tokens, Lexend, and the spacing scale.
   Hardcoded colors in components fail review.
4. **Light mode only** (v1). The brand defines no dark ramp; do not invent one.

## 2. Brand foundations

| Token | Value | Use |
|---|---|---|
| `primary` | `#ea1b3d` | Brand crimson — fills and crimson text alike (exact, everywhere) |
| `primary-hover` | `#c53030` | Hover on filled primary |
| `background` (page) | `#fff9ed` | Cream ground — the standard page surface |
| `card` | `#ffffff` | White cards on cream |
| `foreground` | `#373742` | Primary text |
| `muted-foreground` | `#676775` | Secondary text |
| `sidebar` | `#2f2f39` | Dark charcoal chrome |
| `success` / `warning` | `#0d8244` / `#bf8208` | Status |

- **Type: Lexend.** Headings **700**. Body 16px/1.5 · small 14px · caption 12px.
  Scale: display 52 · h1 41 · h2 35 · h3 32 · h4 24. Buttons 16px/400.
- **Spacing scale (only these): `4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80`.** No custom values.
- **Radius: `0` on cards *and* controls.** Squared throughout.
- **Layout:** content max-width `1320px`, 12 columns, 24px gutter.
- **Motion:** `0.2s` fast / `0.25s` base / `0.5s` long; `ease-in-out`, `cubic-bezier(0.25,1,0.5,1)`.
  Always honor `prefers-reduced-motion`.

## 3. The crimson exception (accepted, deliberate)

Brand fidelity wins for this one pairing. **Use exact `#ea1b3d` everywhere** — fills and crimson
text — with normal 16px labels. Measured and knowingly accepted:

| Pairing | Ratio | AA requirement | Status |
|---|---|---|---|
| White text on `#ea1b3d` (filled buttons) | **4.45:1** | 4.5:1 | accepted miss (~1% short) |
| `#ea1b3d` text on white/cream (links, tab labels) | **4.05:1** | 4.5:1 | accepted miss |

Do **not** "fix" these by substituting a darker red or enlarging labels — that was explicitly
rejected. Everything else still meets AA: body text 11:1, secondary 5.3:1, status chips use
AA-tuned fg/bg pairs (≥4.5:1), focus ring and control borders ≥3:1.
Selection on dark chrome uses a crimson **tint** + white label (that pairing stays high-contrast).

## 4. Logo rules
- **Black wordmark on light grounds** (cream/white): sign-in, footers, documents.
- **White/red wordmark on dark grounds**: charcoal sidebars/headers.
- Never recolor, restretch, or rebuild the mark. Use the supplied SVGs.

## 5. Mandatory app furniture
Every InfoBeans app ships these without being asked:
- **Footer meta on every screen** — `Copyright © <year> InfoBeans Technologies Limited. All rights
  reserved.` + `Version <x.y.z>`.
- **Table pagination on every data table** — page controls (first/prev/next/last), a page indicator,
  a row count (`1–25 of 120`), and a **page-size selector: 10 / 25 / 50 / 100**.

## 6. Selection & interaction states
- Tabs/nav selection is **crimson**, expressed as label color + surface — **no indicator bars**.
- Focus is always visible (brand focus ring).
- Irreversible actions (approve/reject/delete) get a **confirm or an undo**.
- Icon-only controls always carry an `aria-label`.

## 7. Component substrate
**shadcn/ui on Vite + React + TypeScript + Tailwind v4**, themed via CSS variables.
See `03-SHADCN-SETUP.md`.

## 8. Documented deviations from `DESIGN-infobeans-ai.md`
Recorded so they aren't "corrected" back by mistake:

| Brand doc says | We do | Why |
|---|---|---|
| Radius 4px controls / 8px cards | **0px everywhere** | Explicit user standard |
| Accent blue `#1eaedb` for links & nav | **No blue — crimson only** | Explicit user decision; blue is absent from the Figma system |
| Pink offset shadow `4px 4px 0 0 #ffd0d8` | **Not used** | Explicit user decision |
| Input border `#e5e7eb` | **AA-compliant border** | `#e5e7eb` is ~1.2:1; kept compliant since it isn't covered by the §3 exception |
| Checkbox checked = blue `rgb(24,99,220)` | **Crimson** | Doc scopes that blue to the cookie banner only |

## 9. Sources
- `DESIGN-infobeans-ai.md` — brand spec (colors, type, spacing, motion, components)
- Figma design system `QjyYqJkWxmlLjW3LJicGIz` — product token source
- Logos: `Logo_black.svg`, `Logo_White-Red.svg`
- Reference implementation: the InfoBeans Attendance Portal (reference build)
