import { ChevronDown, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";

// One part of a longer form, as its own panel: a soft cream title bar with a crimson edge, an icon,
// a plain title and a line saying what the part is for, then its fields. `optional` says so next to
// the title, so a part that can be skipped never looks required.
//
// `collapsible` lets the person close the panel from its title bar and open it again; while closed,
// `closedSummary` (when given) replaces the description, so they still see what is chosen inside.
export function FormSection({
  icon: Icon,
  title,
  description,
  optional = false,
  collapsible = false,
  defaultOpen = true,
  closedSummary,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  optional?: boolean;
  collapsible?: boolean;
  defaultOpen?: boolean;
  closedSummary?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const heading = (
    <>
      <span
        aria-hidden="true"
        className="mt-0.5 flex size-9 shrink-0 items-center justify-center bg-card text-primary shadow-xs"
      >
        <Icon className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="flex flex-wrap items-center gap-2 text-lg font-bold leading-tight text-foreground">
          {title}
          {optional && (
            <span className="border border-border bg-card px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              Optional
            </span>
          )}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {collapsible && !open && closedSummary ? closedSummary : description}
        </p>
      </div>
    </>
  );

  const headerClass =
    "flex items-start gap-3 border-l-4 border-l-primary bg-secondary/70 px-5 py-4";

  if (!collapsible) {
    return (
      <section className="border border-border bg-card shadow-xs">
        <header className={`${headerClass} border-b border-border`}>
          {heading}
        </header>
        <div className="flex flex-col gap-4 px-5 py-5">{children}</div>
      </section>
    );
  }

  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="group border border-border bg-card shadow-xs"
    >
      <summary
        className={`${headerClass} cursor-pointer list-none group-open:border-b group-open:border-border focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden`}
      >
        {heading}
        <span className="mt-1.5 flex shrink-0 items-center gap-1 text-xs font-medium text-muted-foreground">
          <span className="hidden sm:inline">{open ? "Hide" : "Show"}</span>
          <ChevronDown
            className="size-5 transition-transform duration-150 group-open:rotate-180 motion-reduce:transition-none"
            aria-hidden="true"
          />
        </span>
      </summary>
      <div className="flex flex-col gap-4 px-5 py-5">{children}</div>
    </details>
  );
}
