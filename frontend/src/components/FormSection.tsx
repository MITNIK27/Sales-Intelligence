import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

// One part of a longer form, as its own panel: a soft cream title bar with a crimson edge, an icon,
// a plain title and a line saying what the part is for, then its fields. `optional` says so next to
// the title, so a part that can be skipped never looks required.
export function FormSection({
  icon: Icon,
  title,
  description,
  optional = false,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="border border-border bg-card shadow-xs">
      <header className="flex items-start gap-3 border-b border-border border-l-4 border-l-primary bg-secondary/70 px-5 py-4">
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
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
      </header>
      <div className="flex flex-col gap-4 px-5 py-5">{children}</div>
    </section>
  );
}
