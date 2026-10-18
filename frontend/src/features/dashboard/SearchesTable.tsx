import { ChevronRight, Compass } from "lucide-react";
import { Link } from "react-router-dom";

import type { DashboardRunStats } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonLines } from "@/components/Skeleton";
import { TablePagination } from "@/components/TablePagination";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RunStatusChip } from "@/features/dashboard/RunStatusChip";
import { formatNumber, plural, shortDate } from "@/lib/format";

// Header cells share one quiet style so the numbers, not the labels, carry the weight.
const CELL = "border-r border-border last:border-r-0";
const HEAD = `${CELL} h-10 px-3 text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground`;
const NUM = `${CELL} px-3 py-4 text-right text-sm tabular-nums`;

// One row per search. A row is a single click target (the whole row opens that search on this page),
// marked by a hover tint and a chevron, so "how did this market do" is one click away.
export function SearchesTable({
  items,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onPageSizeChange,
  onSelect,
}: {
  items: DashboardRunStats[] | null;
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  onPageChange: (p: number) => void;
  onPageSizeChange: (s: number) => void;
  onSelect: (runId: string) => void;
}) {
  if (loading && items === null)
    return <SkeletonLines lines={4} className="px-5 pb-5" />;
  if (!items || items.length === 0) {
    return (
      <EmptyState
        icon={Compass}
        title="Run your first search"
        description="Describe a market in the box above. We find the companies, check them against your requirements and suggest who to contact."
        action={
          <Button asChild variant="outline">
            <Link to="/market-discovery">Open Market Discovery</Link>
          </Button>
        }
      />
    );
  }
  // A single page needs no pager: just say how many there are. Paging appears when there is more.
  const singlePage = total <= pageSize && page === 1;
  return (
    <div>
      <div className="mx-5 overflow-x-auto border border-border">
        <Table className="min-w-[680px] table-fixed">
          <colgroup>
            <col />
            <col className="w-28" />
            <col className="w-28" />
            <col className="w-24" />
            <col className="w-24" />
            <col className="w-20" />
            <col className="w-12" />
          </colgroup>
          <TableHeader>
            <TableRow className="border-b border-border bg-muted/50 hover:bg-muted/50">
              <TableHead className={`${HEAD} pl-4`}>Search</TableHead>
              <TableHead className={HEAD}>Status</TableHead>
              <TableHead className={`${HEAD} text-right`}>Companies</TableHead>
              <TableHead className={`${HEAD} text-right`}>Fit</TableHead>
              <TableHead className={`${HEAD} text-right`}>Drafts</TableHead>
              <TableHead className={`${HEAD} text-right`}>Score</TableHead>
              <TableHead className="w-12">
                <span className="sr-only">Open</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((run) => (
              <TableRow
                key={run.run_id}
                className="group cursor-pointer hover:bg-primary/5"
                onClick={() => onSelect(run.run_id)}
              >
                <TableCell
                  className={`${CELL} py-4 pl-4 pr-3 whitespace-normal`}
                >
                  <button
                    type="button"
                    className="line-clamp-2 text-left text-sm font-semibold leading-snug hover:underline focus-visible:outline-2 focus-visible:outline-primary"
                    title={run.title}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelect(run.run_id);
                    }}
                  >
                    {run.title}
                  </button>
                  <p
                    className="mt-1 truncate text-xs text-muted-foreground"
                    title={run.summary}
                  >
                    {shortDate(run.created_at)}
                  </p>
                </TableCell>
                <TableCell className={`${CELL} px-3 py-4`}>
                  <RunStatusChip status={run.status} />
                </TableCell>
                <TableCell className={NUM}>
                  {formatNumber(run.companies)}
                </TableCell>
                <TableCell className={NUM}>
                  <span className="font-semibold">{formatNumber(run.fit)}</span>
                  {run.needs_closer_look > 0 && (
                    <span
                      className="ml-1.5 inline-block bg-chip-warning-bg px-1.5 py-0.5 text-xs font-medium text-chip-warning-fg"
                      title={`${run.needs_closer_look} more need a closer look: a requirement could not be verified`}
                    >
                      +{run.needs_closer_look}
                    </span>
                  )}
                </TableCell>
                <TableCell className={NUM}>
                  {formatNumber(run.drafts)}
                </TableCell>
                <TableCell className={NUM}>
                  {run.top_score != null ? Math.round(run.top_score) : "—"}
                </TableCell>
                <TableCell className="py-4 pr-4 text-right">
                  <ChevronRight
                    className="ml-auto size-4 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-primary-text"
                    aria-hidden="true"
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {singlePage ? (
        <p className="px-5 pt-3 text-sm text-muted-foreground">
          {formatNumber(total)} {plural(total, "search", "searches")}
        </p>
      ) : (
        <TablePagination
          total={total}
          page={page}
          pageSize={pageSize}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      )}
    </div>
  );
}
