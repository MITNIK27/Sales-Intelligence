import { useEffect, useState } from "react";

import { apiGet, apiPost } from "@/api/client";
import type { OfferingCoverage, OfferingPageVerdict } from "@/api/types";
import { ErrorState } from "@/components/ErrorState";
import { InfoTip } from "@/components/InfoTip";
import { SkeletonLines } from "@/components/Skeleton";
import { TablePagination } from "@/components/TablePagination";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { WebsiteLink } from "@/components/WebsiteLink";
import {
  LANE_LABEL,
  MENU_STATUS_LABEL,
  VERDICT_LABEL,
  canTreatAsOffering,
  filterPages,
  menuSummary,
  needsAttention,
  pageSlice,
  sortMenu,
  splitScreened,
} from "@/features/products/coverage";
import { formatNumber, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const VERDICTS: (OfferingPageVerdict | "all")[] = ["all", "offering", "not_offering", "failed"];

// "What was checked": every page the importer looked at and what it concluded, and the website
// menu checked against the catalogue, so a missing offering is never a mystery.
export function CoveragePanel({
  onCheckStarted,
  onRunCheck,
}: {
  onCheckStarted: () => void;
  onRunCheck: () => void;
}) {
  const [coverage, setCoverage] = useState<OfferingCoverage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [verdict, setVerdict] = useState<OfferingPageVerdict | "all">("all");
  const [showScreened, setShowScreened] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [newUrl, setNewUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  function load() {
    setError(null);
    return apiGet<OfferingCoverage>("/products/coverage")
      .then(setCoverage)
      .catch((err) => setError(err instanceof Error ? err.message : "could not load coverage"));
  }

  useEffect(() => {
    load();
  }, []);

  async function treatAsOffering(url: string) {
    setBusy(true);
    setActionError(null);
    try {
      await apiPost("/products/coverage/check", { url });
      setNewUrl("");
      onCheckStarted();
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "could not queue the page");
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <Card className="mb-6">
        <ErrorState message={error} onRetry={load} />
      </Card>
    );
  }
  if (!coverage) {
    return (
      <Card className="mb-6 p-6">
        <SkeletonLines lines={4} />
      </Card>
    );
  }

  const menu = coverage.menu ? sortMenu(coverage.menu) : null;
  const { summary } = coverage;
  const { main, screened } = splitScreened(coverage.pages);
  // Searching looks everywhere, including the screened-out posts; otherwise they stay folded away.
  const searching = query.trim() !== "";
  const pool = showScreened || searching ? coverage.pages : main;
  const matching = filterPages(pool, query, verdict);
  const { rows, page: currentPage } = pageSlice(matching, page, pageSize);

  return (
    <Card className="mb-6 p-0">
      <section className="border-b border-border px-5 py-4" aria-labelledby="menu-check">
        <h2 id="menu-check" className="flex items-center gap-2 text-base font-semibold">
          Website menu check
          <InfoTip label="About the website menu check">
            The company's own website menu lists what it puts forward. Each entry should be in the
            catalogue; anything marked "Not imported" is a possible gap.
          </InfoTip>
        </h2>
        {menu ? (
          <>
            <p className="mt-1 text-sm text-muted-foreground">
              {menuSummary(menu).attention === 0
                ? `Everything in the website menu (${menu.length}) is in the catalogue.`
                : `${menuSummary(menu).attention} of ${menu.length} entries in the website menu need a look.`}
            </p>
            <ul className="mt-3 flex flex-col gap-1.5">
              {menu.map((item) => (
                <li key={item.url} className="flex flex-wrap items-center gap-2 text-sm">
                  <span
                    className={cn(
                      "px-2 py-0.5 text-xs font-medium",
                      item.status === "covered"
                        ? "bg-chip-success-bg text-chip-success-fg"
                        : item.status === "judged_not_offering"
                          ? "bg-muted text-muted-foreground"
                          : "bg-chip-warning-bg text-chip-warning-fg",
                    )}
                  >
                    {MENU_STATUS_LABEL[item.status]}
                  </span>
                  <span className="font-medium">{item.label}</span>
                  <span className="text-xs text-muted-foreground">{item.group}</span>
                  <WebsiteLink domain={item.url} className="text-xs" />
                  {needsAttention(item) && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => treatAsOffering(item.url)}
                    >
                      Read as an offering
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span>
              {coverage.menu_error ??
                "Run a check for updates to compare the website menu with the catalogue."}
            </span>
            <Button type="button" size="sm" variant="outline" onClick={onRunCheck}>
              Check again
            </Button>
          </div>
        )}
        {menu && coverage.menu_error && (
          <p className="mt-2 text-sm text-destructive">{coverage.menu_error}</p>
        )}
      </section>

      <section className="px-5 py-4" aria-labelledby="pages-checked">
        <h2 id="pages-checked" className="flex items-center gap-2 text-base font-semibold">
          Pages checked
          <InfoTip label="About the pages checked">
            Every page the check looked at, with what it decided and why. If something is missing
            from the catalogue, find its page here, and use "Read as an offering" to ask for it to
            be read again.
          </InfoTip>
        </h2>
        <p className="mt-1 text-sm text-muted-foreground tabular-nums">
          {formatNumber(summary.total)} pages · {formatNumber(summary.offering)} offerings ·{" "}
          {formatNumber(summary.not_offering)} not offerings · {formatNumber(summary.failed)} could
          not be read
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search by address or title"
            aria-label="Search checked pages"
            className="w-72 bg-card"
          />
          <div role="group" aria-label="Filter by result" className="flex flex-wrap gap-1">
            {VERDICTS.map((v) => (
              <Button
                key={v}
                type="button"
                size="sm"
                variant={verdict === v ? "default" : "outline"}
                aria-pressed={verdict === v}
                onClick={() => {
                  setVerdict(v);
                  setPage(1);
                }}
              >
                {v === "all" ? "All" : VERDICT_LABEL[v]}
              </Button>
            ))}
          </div>
        </div>

        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (newUrl.trim()) treatAsOffering(newUrl.trim());
          }}
        >
          <Input
            type="url"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            placeholder="https://… add a page to read as an offering"
            aria-label="Address of a page to add"
            className="w-96 max-w-full bg-card"
          />
          <Button type="submit" size="sm" variant="outline" disabled={busy || !newUrl.trim()}>
            Add page
          </Button>
        </form>
        {actionError && <p className="mt-2 text-sm text-destructive">{actionError}</p>}

        {screened.length > 0 && !searching && (
          <button
            type="button"
            aria-expanded={showScreened}
            onClick={() => {
              setShowScreened(!showScreened);
              setPage(1);
            }}
            className="mt-4 text-sm text-primary-text hover:underline focus-visible:outline-2 focus-visible:outline-primary"
          >
            {showScreened
              ? "Hide blog posts that were set aside"
              : `Show ${formatNumber(screened.length)} blog posts that were set aside from their title`}
          </button>
        )}

        <div className="mt-3 border border-border">
          {rows.length === 0 && (
            <p className="px-4 py-3 text-sm text-muted-foreground">No pages match.</p>
          )}
          {rows.map((row) => (
            <div
              key={row.url}
              className="grid grid-cols-1 items-center gap-x-4 gap-y-1 border-b border-border px-4 py-2 text-sm last:border-b-0 md:grid-cols-[9rem_minmax(0,1.4fr)_minmax(0,1fr)_9.5rem]"
            >
              <span className="text-xs text-muted-foreground">{VERDICT_LABEL[row.verdict]}</span>
              <div className="min-w-0 truncate">
                <WebsiteLink domain={row.url} className="text-sm" />
              </div>
              <span
                className="min-w-0 truncate text-xs text-muted-foreground"
                title={detailText(row)}
              >
                {detailText(row)}
              </span>
              <div className="md:text-right">
                {canTreatAsOffering(row) && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => treatAsOffering(row.url)}
                  >
                    Read as an offering
                  </Button>
                )}
              </div>
            </div>
          ))}
          <TablePagination
            total={matching.length}
            page={currentPage}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(1);
            }}
          />
        </div>
      </section>
    </Card>
  );
}

function detailText(row: OfferingCoverage["pages"][number]): string {
  const parts = [LANE_LABEL[row.lane]];
  if (row.reason) parts.push(row.reason);
  if (row.last_checked_at) parts.push(`checked ${timeAgo(row.last_checked_at)}`);
  if (row.force_extract) parts.push("will be read next check");
  return parts.join(" · ");
}
