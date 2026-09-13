# Component Patterns

Working code for the pieces that make an app *look and behave* like InfoBeans. The footer and the
table pagination are **mandatory** in every app (standards §5) — ship them from day one.

All of these bind to theme tokens only. Copy them as-is.

---

## 1. App shell — sidebar + topbar + footer

The signature InfoBeans app layout: charcoal sidebar, white topbar, cream content, footer meta.

```tsx
// src/layout/AppLayout.tsx
import { Outlet } from "react-router-dom"
import { AppSidebar } from "@/components/AppSidebar"
import { Topbar } from "@/components/Topbar"
import { AppFooter } from "@/components/AppFooter"

export function AppLayout() {
  return (
    <div className="grid min-h-screen grid-cols-[248px_1fr] grid-rows-[60px_1fr] bg-background">
      <AppSidebar />
      <Topbar />
      <div className="col-start-2 row-start-2 flex min-h-0 flex-col overflow-y-auto">
        <main className="mx-auto w-full max-w-[1320px] flex-1 p-8">
          <Outlet />
        </main>
        <AppFooter />
      </div>
    </div>
  )
}
```

### Sidebar — grouped nav, role-aware, crimson tint selection

```tsx
// src/components/AppSidebar.tsx  (excerpt)
<aside className="row-span-2 w-62 bg-sidebar text-sidebar-foreground flex flex-col">
  <div className="flex h-15 items-center px-6">
    <Logo on="dark" className="h-7" />
  </div>
  <nav className="flex-1 overflow-y-auto px-3 py-4">
    {groups.map((g) => (
      <div key={g.title} className="mb-6">
        <h4 className="px-3 py-2 text-xs font-medium uppercase tracking-[0.12em] text-white/45">
          {g.title}
        </h4>
        {g.items.map((it) => (
          <NavLink key={it.to} to={it.to} end={it.end}
            className={({ isActive }) => cn(
              "flex w-full items-center gap-3 px-4 py-3 text-base text-white/80 transition-colors duration-200",
              "hover:bg-white/6 hover:text-white",
              // selection = crimson tint, NO indicator bar
              isActive && "bg-primary/25 text-white font-semibold",
            )}>
            <it.icon className="size-4 opacity-85" />
            <span>{it.label}</span>
            {it.badge && <span className="ml-auto text-xs text-white/45">{it.badge}</span>}
          </NavLink>
        ))}
      </div>
    ))}
  </nav>
</aside>
```

**Group the nav by ownership**, not by feature list — e.g. *My Work* / *My Team* / *Reference*.
Role-gate whole groups so people only see what their role needs.

---

## 2. Footer meta — MANDATORY on every screen

```tsx
// src/lib/app-meta.ts
export const APP_NAME = "<Your App>"
export const APP_VERSION = "1.0.0"
export const COPYRIGHT_YEAR = new Date().getFullYear()
export const COPYRIGHT_OWNER = "InfoBeans Technologies Limited"
```

```tsx
// src/components/AppFooter.tsx
import { APP_VERSION, COPYRIGHT_OWNER, COPYRIGHT_YEAR } from "@/lib/app-meta"
import { cn } from "@/lib/utils"

export function AppFooter({ className }: { className?: string }) {
  return (
    <footer className={cn(
      "flex flex-wrap items-center justify-between gap-2 border-t border-border px-8 py-4 text-xs text-muted-foreground",
      className,
    )}>
      <span>
        Copyright © {COPYRIGHT_YEAR}{" "}
        <span className="font-medium text-foreground">{COPYRIGHT_OWNER}</span>. All rights reserved.
      </span>
      <span>Version {APP_VERSION}</span>
    </footer>
  )
}
```

Include it on **auth screens too** (sign-in), not just the app shell.

---

## 3. Table pagination — MANDATORY on every data table

```tsx
// src/components/TablePagination.tsx
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight } from "lucide-react"

export const PAGE_SIZES = [10, 25, 50, 100]

interface Props {
  total: number; page: number; pageSize: number
  onPageChange: (p: number) => void
  onPageSizeChange: (s: number) => void
}

export function TablePagination({ total, page, pageSize, onPageChange, onPageSizeChange }: Props) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const current = Math.min(page, pageCount)
  const first = total === 0 ? 0 : (current - 1) * pageSize + 1
  const last = Math.min(current * pageSize, total)
  const go = (p: number) => onPageChange(Math.min(Math.max(1, p), pageCount))

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Rows per page</span>
        <Select value={String(pageSize)} onValueChange={(v) => { onPageSizeChange(Number(v)); onPageChange(1) }}>
          <SelectTrigger className="h-9 w-20 bg-card" aria-label="Rows per page"><SelectValue /></SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((s) => <SelectItem key={s} value={String(s)}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground tabular-nums">{first}–{last} of {total}</span>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" className="size-9" aria-label="First page"
            disabled={current === 1} onClick={() => go(1)}><ChevronsLeft className="size-4" /></Button>
          <Button variant="outline" size="icon" className="size-9" aria-label="Previous page"
            disabled={current === 1} onClick={() => go(current - 1)}><ChevronLeft className="size-4" /></Button>
          <span className="px-2 text-sm tabular-nums">Page {current} of {pageCount}</span>
          <Button variant="outline" size="icon" className="size-9" aria-label="Next page"
            disabled={current === pageCount} onClick={() => go(current + 1)}><ChevronRight className="size-4" /></Button>
          <Button variant="outline" size="icon" className="size-9" aria-label="Last page"
            disabled={current === pageCount} onClick={() => go(pageCount)}><ChevronsRight className="size-4" /></Button>
        </div>
      </div>
    </div>
  )
}
```

Usage — slice the filtered rows, and reset to page 1 whenever a filter changes:
```tsx
const filtered = data.filter(...)
const rows = filtered.slice((page - 1) * pageSize, page * pageSize)
// …<TablePagination total={filtered.length} page={page} pageSize={pageSize} … />
```

---

## 4. Status chips — never raw codes

Replace codes like `P` / `A` / `HD` with human labels in AA-tuned chips.

```tsx
// src/components/StatusBadge.tsx
const map = {
  pending:  { label: "Pending",  cls: "bg-chip-warning-bg text-chip-warning-fg" },
  approved: { label: "Approved", cls: "bg-chip-success-bg text-chip-success-fg" },
  rejected: { label: "Rejected", cls: "bg-chip-rejected-bg text-chip-rejected-fg" },
}

export function StatusBadge({ status }: { status: keyof typeof map }) {
  const { label, cls } = map[status]
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold uppercase tracking-wide", cls)}>
      <span className="size-1.5 rounded-full bg-current" />
      {label}
    </span>
  )
}
```

---

## 5. Page header pattern

Consistent across every screen — eyebrow, bold title, one-line description, primary action right.

```tsx
<div className="mb-6 flex items-end justify-between">
  <div>
    <div className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">Group</div>
    <h1 className="text-3xl font-bold">Screen title</h1>
    <p className="mt-1 text-base text-muted-foreground">One line on what this screen is for.</p>
  </div>
  <Button>+ Primary action</Button>
</div>
```

---

## 6. Required states

Standards §1.2 — every screen designs all four. Patterns:

```tsx
// Loading — skeleton, motion-safe
<div className="my-2 h-4 w-4/5 rounded bg-muted motion-safe:animate-pulse" />

// Empty — icon, what happened, what to do next
<div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
  <div className="grid size-12 place-items-center bg-secondary"><Icon className="size-6 text-warning" /></div>
  <div>
    <h3 className="text-lg font-bold">Nothing here yet</h3>
    <p className="text-sm text-muted-foreground">Explain what will appear and why.</p>
  </div>
  <Button variant="outline">Primary next step</Button>
</div>

// Error — say what failed and how to recover, then a retry action.
```

---

## 7. Irreversible actions get an undo

```tsx
import { toast } from "sonner"

const decide = (i: number, d: "approved" | "rejected") => {
  applyDecision(i, d)
  toast(`Request ${d}`, { action: { label: "Undo", onClick: () => undo([i]) } })
}
```

Mount `<Toaster />` once at the root. Icon-only buttons always get an `aria-label`.
