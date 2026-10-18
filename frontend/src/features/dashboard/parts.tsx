import { ArrowRight, Check, CircleHelp, X } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { SectionTitle } from "@/features/dashboard/SectionTitle";
import { cn } from "@/lib/utils";

// One titled card used by every block on the dashboard: a title, the content, and an optional quiet
// link underneath. No description paragraph; anything that needs explaining goes in a `title`.
export function Panel({
  title,
  action,
  footerLink,
  flush = false,
  className,
  children,
}: {
  title: string;
  action?: ReactNode;
  footerLink?: { to: string; label: string };
  flush?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card className={cn("h-full [--card-spacing:--spacing(5)]", className)}>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <SectionTitle>{title}</SectionTitle>
          {action}
        </div>
      </CardHeader>
      <CardContent className={cn("flex-1", flush && "px-0")}>
        {children}
      </CardContent>
      {footerLink && (
        <div className="px-(--card-spacing)">
          <Link
            to={footerLink.to}
            className="inline-flex items-center gap-1 text-sm text-primary-text hover:underline focus-visible:outline-2 focus-visible:outline-primary"
          >
            {footerLink.label}{" "}
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        </div>
      )}
    </Card>
  );
}

export type BarSegment = { value: number; className: string };

// A thin horizontal bar made of one or more segments, used by the funnel, the requirement results
// and the credit gauge. Widths are percentages of `total`; the label is read out for screen readers
// because colour alone never carries the meaning.
export function MetricBar({
  segments,
  total,
  label,
  height = "h-1.5",
}: {
  segments: BarSegment[];
  total: number;
  label: string;
  height?: string;
}) {
  return (
    <div
      className={cn("flex w-full overflow-hidden bg-muted", height)}
      role="img"
      aria-label={label}
    >
      {segments.map((segment, index) => (
        <div
          key={index}
          className={cn(
            segment.className,
            "transition-[width] duration-500 motion-reduce:transition-none",
          )}
          style={{
            width: `${total <= 0 ? 0 : Math.min(100, (segment.value / total) * 100)}%`,
          }}
        />
      ))}
    </div>
  );
}

const STATUS = {
  meets: { Icon: Check, cls: "text-chip-success-fg", word: "meet" },
  unverified: {
    Icon: CircleHelp,
    cls: "text-chip-warning-fg",
    word: "could not be verified",
  },
  fails: { Icon: X, cls: "text-chip-rejected-fg", word: "do not meet" },
} as const;

// An icon and a number ("✓ 9"), coloured by outcome. The icon makes the outcome readable without
// colour, and the full sentence is on the title for hover and screen readers.
export function StatusCount({
  kind,
  count,
}: {
  kind: keyof typeof STATUS;
  count: number;
}) {
  const { Icon, cls, word } = STATUS[kind];
  return (
    <span
      className={cn("inline-flex items-center gap-1 tabular-nums", cls)}
      title={`${count} ${word}`}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      <span className="sr-only">{`${count} ${word}`}</span>
      <span aria-hidden="true">{count}</span>
    </span>
  );
}
