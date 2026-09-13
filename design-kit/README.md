# InfoBeans Design Kit

Everything Claude Code needs to design and build a **new application that looks purely like an
InfoBeans product** — brand standards, a paste-ready theme, the build setup, the mandatory
component patterns, the logos, and the design process.

Self-contained. Nothing else is required.

---

## How to use it

1. Copy this whole folder into your new project (e.g. `./design-kit/`).
2. Open Claude Code in that project and say:

> Read every file in `./design-kit/`, starting with `01-BRAND-STANDARDS.md`. These are
> non-negotiable standards for all InfoBeans applications — apply them without asking me to
> restate them. Then build **&lt;your app&gt;**: &lt;what it does, who uses it&gt;.

That's it. Claude will scaffold a Vite + React + TS + shadcn app, apply the InfoBeans theme, and
build screens that inherit the brand.

**Pin the standards for every future session** by adding this line to your project's `CLAUDE.md`:

```md
Before creating any UI, read ./design-kit/01-BRAND-STANDARDS.md and 02-THEME.md. These are
inherited standards for InfoBeans applications — never ask the user to restate them.
```

---

## What's in here

| File | Read | Purpose |
|---|---|---|
| **01-BRAND-STANDARDS.md** | **Always** | The core values and brand law. Non-negotiables, foundations, logo rules, mandatory app furniture, and the documented deviations. |
| **02-THEME.md** | **Always** | Paste-ready `index.css` — the InfoBeans theme mapped onto shadcn's CSS-variable contract. Drop it in and the app is on-brand. |
| **03-SHADCN-SETUP.md** | To build | Reproducible Vite + React + TS + Tailwind v4 + shadcn setup, including the gotchas that break the CLI. |
| **04-COMPONENT-PATTERNS.md** | To build | Working code for the pieces the standards *require*: app shell, footer meta, table pagination, status chips, logo. |
| **05-LOGO-ASSETS.md** | To build | Both logo SVGs inline + the light/dark usage rule. |
| **06-DESIGN-PROCESS.md** | Recommended | The end-to-end method: discovery → strategy → design → validation → production, with the artifact each stage hands on. |

## The five-second version

Cream page `#fff9ed`, white cards, charcoal `#2f2f39` chrome, crimson `#ea1b3d`, **Lexend** with
700 headings, **0px radius everywhere**, spacing from `[4…80]`, light mode only. Every screen ends
with a copyright + version footer; every data table has pagination with a page-size selector.
Accessibility is a hard gate — with one documented exception (the crimson pairing).

## Provenance
Derived from the InfoBeans brand spec (`DESIGN-infobeans-ai.md`), the Figma design system
`QjyYqJkWxmlLjW3LJicGIz`, and the official logo assets. Reference implementation: the InfoBeans
Attendance Portal redesign.
