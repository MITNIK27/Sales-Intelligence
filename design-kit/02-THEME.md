# InfoBeans Theme — paste-ready

This is the whole visual identity as code. Drop it into `src/index.css` of a Vite + React +
Tailwind v4 + shadcn app (see `03-SHADCN-SETUP.md`) and the app is on-brand.

**Rule: components bind to these tokens. Never hardcode a hex in a component.**

---

## 1. Install the font

Lexend is the brand typeface. Bundle it — don't rely on a CDN link (CSP-blocked in sandboxes,
and it silently falls back):

```bash
npm install @fontsource-variable/lexend
```

```ts
// src/main.tsx — before importing index.css
import '@fontsource-variable/lexend'
import './index.css'
```

## 2. `src/index.css`

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";

@custom-variant dark (&:is(.dark *));

/* =============================================================================
   InfoBeans theme for shadcn/ui — brand tokens mapped onto shadcn's variable
   contract. Light-only (the brand defines no dark ramp).
   ============================================================================= */
@theme inline {
    --font-heading: var(--font-sans);
    --font-sans: 'Lexend Variable', 'Lexend', sans-serif;
    --color-sidebar-ring: var(--sidebar-ring);
    --color-sidebar-border: var(--sidebar-border);
    --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
    --color-sidebar-accent: var(--sidebar-accent);
    --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
    --color-sidebar-primary: var(--sidebar-primary);
    --color-sidebar-foreground: var(--sidebar-foreground);
    --color-sidebar: var(--sidebar);
    --color-chart-5: var(--chart-5);
    --color-chart-4: var(--chart-4);
    --color-chart-3: var(--chart-3);
    --color-chart-2: var(--chart-2);
    --color-chart-1: var(--chart-1);
    --color-ring: var(--ring);
    --color-input: var(--input);
    --color-border: var(--border);
    --color-destructive: var(--destructive);
    --color-accent-foreground: var(--accent-foreground);
    --color-accent: var(--accent);
    --color-muted-foreground: var(--muted-foreground);
    --color-muted: var(--muted);
    --color-secondary-foreground: var(--secondary-foreground);
    --color-secondary: var(--secondary);
    --color-primary-foreground: var(--primary-foreground);
    --color-primary: var(--primary);
    --color-primary-hover: var(--primary-hover);
    --color-primary-text: var(--primary-text);
    --color-popover-foreground: var(--popover-foreground);
    --color-popover: var(--popover);
    --color-card-foreground: var(--card-foreground);
    --color-card: var(--card);
    --color-foreground: var(--foreground);
    --color-background: var(--background);
    /* status extensions */
    --color-success: var(--success);
    --color-success-foreground: var(--success-foreground);
    --color-warning: var(--warning);
    --color-warning-foreground: var(--warning-foreground);
    /* status chips — AA-tuned fg/bg pairs (≥4.5:1 for 12px text) */
    --color-chip-warning-fg: var(--chip-warning-fg);
    --color-chip-warning-bg: var(--chip-warning-bg);
    --color-chip-success-fg: var(--chip-success-fg);
    --color-chip-success-bg: var(--chip-success-bg);
    --color-chip-rejected-fg: var(--chip-rejected-fg);
    --color-chip-rejected-bg: var(--chip-rejected-bg);
    --radius-sm: calc(var(--radius) * 0.6);
    --radius-md: calc(var(--radius) * 0.8);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) * 1.4);
    --radius-2xl: calc(var(--radius) * 1.8);
    --radius-3xl: calc(var(--radius) * 2.2);
    --radius-4xl: calc(var(--radius) * 2.6);
}

:root {
    /* Surfaces — cream-forward page, white cards */
    --background: #fff9ed;
    --foreground: #373742;
    --card: #ffffff;
    --card-foreground: #373742;
    --popover: #ffffff;
    --popover-foreground: #373742;
    /* Brand — exact InfoBeans crimson, used everywhere. White-on-crimson is
       4.45:1: a documented, accepted AA exception (standards §3). Labels stay 16px. */
    --primary: #ea1b3d;
    --primary-hover: #c53030;
    --primary-foreground: #ffffff;
    --primary-text: #ea1b3d;        /* crimson text on light grounds */
    --secondary: #ffefd1;
    --secondary-foreground: #373742;
    --muted: #f2eee4;
    --muted-foreground: #676775;
    --accent: #ffefd1;
    --accent-foreground: #373742;
    --destructive: #ea1b3d;
    --border: #e6e6ed;
    --input: #82828c;               /* AA-tuned control border: 3.8:1 on white */
    --ring: #ea1b3d;                /* brand focus ring */
    /* Status */
    --success: #0d8244;
    --success-foreground: #edfff5;
    --warning: #bf8208;
    --warning-foreground: #fff9ed;
    /* Status chips — AA-tuned */
    --chip-warning-fg: #8c681f; --chip-warning-bg: #fff3d6;   /* 4.63:1 */
    --chip-success-fg: #0a6636; --chip-success-bg: #edfff5;   /* 6.82:1 */
    --chip-rejected-fg: #aa142d; --chip-rejected-bg: #fde3e7; /* 6.08:1 */
    /* Charts — InfoBeans palette */
    --chart-1: #ea1b3d;
    --chart-2: #0fa958;
    --chart-3: #ecb547;
    --chart-4: #676775;
    --chart-5: #eb4c5e;
    /* InfoBeans standard: 0px on cards AND controls */
    --radius: 0;
    /* Motion */
    --motion-fast: 0.2s;
    --motion-base: 0.25s;
    --motion-long: 0.5s;
    --ease-standard: ease-in-out;
    --ease-decelerate: cubic-bezier(0.25, 1, 0.5, 1);
    /* Sidebar / dark chrome */
    --sidebar: #2f2f39;
    --sidebar-foreground: #d7d7de;
    --sidebar-primary: #ea1b3d;
    --sidebar-primary-foreground: #ffffff;
    --sidebar-accent: #373742;
    --sidebar-accent-foreground: #ffffff;
    --sidebar-border: #373742;
    --sidebar-ring: #ea1b3d;
}

/* Light-only. `.dark` is intentionally left at shadcn defaults — do not ship it
   as "InfoBeans dark mode" without a brand-defined dark ramp. */

@layer base {
  * { @apply border-border outline-ring/50; }
  body { @apply bg-background text-foreground; }
  html { @apply font-sans; }
}
```

## 3. Button override (required)

shadcn's default button doesn't match the brand. Patch `src/components/ui/button.tsx`:

```tsx
// variant
default: "bg-primary text-primary-foreground text-base font-normal min-h-10 hover:bg-primary-hover",
link:    "text-primary-text underline-offset-4 hover:underline",
// size — brand: 8px 16px padding, 40px min height
default: "h-10 gap-2 px-4",
```

## 4. Tab / nav selection override (required)

Selection is crimson **with no indicator bar**. In `src/components/ui/tabs.tsx`, replace the
active-state classes with:

```tsx
"data-active:bg-background data-active:text-primary-text data-active:font-semibold"
```

Sidebar nav active state — a crimson **tint** on charcoal (keeps the white label high-contrast):

```tsx
isActive && "bg-primary/25 text-white font-semibold"
```

## 5. Typography usage

| Role | Class | Value |
|---|---|---|
| Page title (h1) | `text-3xl font-bold` | Lexend 700 |
| Section title (h3/h4) | `text-lg font-bold` | Lexend 700 |
| Body | `text-base` | 16px / 1.5 |
| Small / table cells | `text-sm` | 14px |
| Caption / eyebrow | `text-xs` | 12px |

Eyebrow labels: `text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground`.

## 6. Spacing

Use **only** `4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80` → Tailwind `1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20`.
No `2.5`, `3.5`, `4.5`, `7`, `9`, `11`, `14`. Content caps at `max-w-[1320px]`.

## 7. Verify

```bash
# no hardcoded hex outside the theme
grep -rnE '#[0-9a-fA-F]{3,6}' src/components src/screens | grep -v '/ui/'
```
Should return nothing.
