import { ArrowLeft, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

type Period = "7d" | "30d" | "all";

const ALL = "__all__";

// "Showing [All searches] [All time]" re-scopes the whole page, so a rep moves between the big
// picture and a single market without leaving the dashboard. On the right: how fresh the numbers
// are, a refresh, and a Live marker while a search is still running.
export function ScopeBar({
  searches,
  runId,
  period,
  updatedAt,
  live,
  refreshing,
  onRunChange,
  onPeriodChange,
  onRefresh,
}: {
  searches: { run_id: string; label: string }[];
  runId: string | null;
  period: Period;
  updatedAt: number | null;
  live: boolean;
  refreshing: boolean;
  onRunChange: (runId: string | null) => void;
  onPeriodChange: (period: Period) => void;
  onRefresh: () => void;
}) {
  // Re-render every 30 s so "Updated 2 min ago" keeps counting without refetching anything.
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setTick((n) => n + 1), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-muted-foreground">Showing</span>
        <Select
          value={runId ?? ALL}
          onValueChange={(value) => onRunChange(value === ALL ? null : value)}
        >
          <SelectTrigger
            className="h-9 min-w-48 max-w-96 bg-card"
            aria-label="Search to show"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All searches</SelectItem>
            {searches.map((s) => (
              <SelectItem key={s.run_id} value={s.run_id}>
                {s.label.length > 70 ? `${s.label.slice(0, 68)}…` : s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {runId === null ? (
          <Select
            value={period}
            onValueChange={(value) => onPeriodChange(value as Period)}
          >
            <SelectTrigger
              className="h-9 w-40 bg-card"
              aria-label="Time period"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7d">Last 7 days</SelectItem>
              <SelectItem value="30d">Last 30 days</SelectItem>
              <SelectItem value="all">All time</SelectItem>
            </SelectContent>
          </Select>
        ) : (
          <button
            type="button"
            onClick={() => onRunChange(null)}
            className="inline-flex items-center gap-1 text-primary-text hover:underline"
          >
            <ArrowLeft className="size-3.5" /> Back to all searches
          </button>
        )}
      </div>

      <div className="flex items-center gap-3 text-muted-foreground">
        {live && (
          <span
            className="inline-flex items-center gap-1.5 bg-chip-warning-bg px-2 py-0.5 text-xs font-medium text-chip-warning-fg"
            role="status"
          >
            <span className="size-1.5 animate-pulse rounded-full bg-warning motion-reduce:animate-none" />
            Live
          </span>
        )}
        {updatedAt !== null && (
          <span
            className="text-xs"
            title="The numbers on this page are read-only views of your data."
          >
            Updated {timeAgo(new Date(updatedAt).toISOString())}
          </span>
        )}
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 text-primary-text hover:underline disabled:opacity-60"
        >
          <RefreshCw
            className={cn("size-3.5", refreshing && "animate-spin")}
            aria-hidden="true"
          />
          Refresh
        </button>
      </div>
    </div>
  );
}
