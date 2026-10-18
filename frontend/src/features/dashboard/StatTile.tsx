import { ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";

// One headline number with a short label and a few words underneath. `hint` is the longer
// explanation, shown on hover instead of cluttering the tile.
export function StatTile({
  label,
  value,
  note,
  to,
  hint,
}: {
  label: string;
  value: ReactNode;
  note: ReactNode;
  to?: string;
  hint?: string;
}) {
  const body = (
    <div
      title={hint}
      className={cn(
        "relative flex h-full flex-col gap-1 border border-border bg-card px-5 py-4",
        // A tile that goes somewhere looks like it: arrow, pointer, hover tint and a crimson edge.
        to &&
          "cursor-pointer transition-colors duration-200 hover:border-primary hover:bg-primary/5 group-focus-visible:border-primary",
      )}
    >
      {to && (
        <ArrowUpRight
          className="absolute right-3 top-3 size-4 text-primary-text"
          aria-hidden="true"
        />
      )}
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-3xl font-bold tabular-nums leading-tight">
        {value}
      </span>
      <span className="text-sm text-muted-foreground">{note}</span>
    </div>
  );
  return to ? (
    <Link
      to={to}
      className="group block focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      {body}
    </Link>
  ) : (
    body
  );
}
