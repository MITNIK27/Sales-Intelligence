# Build Setup — Vite + React + TS + Tailwind v4 + shadcn/ui

The standard substrate for every InfoBeans app. These exact steps are validated — including the
two gotchas that otherwise break the shadcn CLI or the TypeScript build.

---

## 1. Scaffold

```bash
npm create vite@latest app -- --template react-ts
cd app && npm install
npm install tailwindcss @tailwindcss/vite
npm install -D @types/node
```

## 2. Wire Tailwind v4 + the `@/*` path alias

`vite.config.ts`:
```ts
import path from "path"
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
})
```

Add to **both** `tsconfig.json` and `tsconfig.app.json` under `compilerOptions`:
```json
"paths": { "@/*": ["./src/*"] }
```

> ⚠️ **Gotcha 1 — do NOT add `baseUrl`.** It's deprecated in TypeScript 7 and makes `tsc -b` fail.
> `paths` alone works.

Seed the CSS so the CLI detects Tailwind:
```bash
printf '@import "tailwindcss";\n' > src/index.css
```

## 3. Initialise shadcn + add components

```bash
npx shadcn@latest init -p nova -b radix --yes --force
npx shadcn@latest add button card table input badge checkbox tabs avatar separator \
  select tooltip dropdown-menu dialog label textarea sonner --yes
```

> ⚠️ **Gotcha 2 — presets are `nova|vega|maia|lyra|mira|luma|sera|rhea`** (not `base-nova`), and
> `init` prompts interactively unless you pass `-p`. `-b radix` selects the Radix primitive base.

**If you added `sonner`:** its generated file imports `next-themes`, which a Vite app doesn't have.
Delete the `useTheme` import and hardcode `theme="light"` (this app is light-only anyway).

## 4. Apply the InfoBeans theme

Replace `src/index.css` with the theme from **`02-THEME.md`**, install the font, and apply the
button + tabs overrides in that file. This is what makes it an InfoBeans app rather than a
default shadcn app.

## 5. Recommended production dependencies

```bash
npm install react-router-dom @tanstack/react-query react-hook-form zod @hookform/resolvers
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Vitest config — note the import is from `vitest/config`, and exclude tests from the app build so
`tsc -b` doesn't type-check them:

```ts
// vite.config.ts
test: { globals: true, environment: "jsdom", setupFiles: ["./src/test/setup.ts"], css: false },
```
```json
// tsconfig.app.json
"exclude": ["src/**/*.test.ts", "src/**/*.test.tsx", "src/test"]
```

## 6. Suggested structure

```
src/
  index.css              ← the InfoBeans theme (source of truth)
  components/ui/*        ← shadcn components (owned, in-repo)
  components/*           ← app chrome: AppSidebar, Topbar, AppFooter, TablePagination, Logo
  screens/*              ← one file per screen
  layout/AppLayout.tsx   ← shell + <Outlet/>
  lib/                   ← api, queries, auth, utils, app-meta
  assets/                ← logo SVGs
```

## 7. Quality gates

```bash
npm run build   # tsc -b && vite build — must pass clean
npm run test
npm run lint
```
Plus the checks in `01-BRAND-STANDARDS.md`: no hardcoded hex, every state designed, AA contrast.

## 8. Shipping a single-file preview (optional)

To produce one self-contained HTML file (easy to share, no server):

```bash
npm install -D vite-plugin-singlefile
```
Enable it behind an env flag, set `build.assetsInlineLimit` very high so fonts/SVGs inline, and
switch the router to `createHashRouter` for that build (static hosting has no server rewrites).
