import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";

import type { DashboardAttentionItem } from "@/api/types";
import { SkeletonLines } from "@/components/Skeleton";
import { attentionLabel } from "@/features/dashboard/metrics";
import { formatNumber } from "@/lib/format";

// What to do next. Rows with nothing to do are dropped, so the list is short and every line is an
// action; when everything is clear it says so.
export function AttentionQueue({
  items,
}: {
  items: DashboardAttentionItem[] | null;
}) {
  if (items === null) return <SkeletonLines lines={3} />;
  const actionable = items.filter((item) => item.count > 0);
  if (actionable.length === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <CheckCircle2 className="size-4 text-success" aria-hidden="true" />
        You are all caught up.
      </p>
    );
  }
  return (
    <ul className="flex flex-col divide-y divide-border">
      {actionable.map((item) => (
        <li key={item.key}>
          <Link
            to={item.href}
            title={item.label}
            className="group -mx-2 flex items-center gap-4 px-2 py-3 transition-colors duration-200 hover:bg-primary/5 hover:text-primary-text focus-visible:outline-2 focus-visible:outline-primary"
          >
            <span className="w-8 text-right text-xl font-bold tabular-nums">
              {formatNumber(item.count)}
            </span>
            <span className="flex-1 text-sm">
              {attentionLabel(item.key, item.label)}
            </span>
            <ArrowRight
              className="size-4 text-primary-text transition-transform duration-200 group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}
