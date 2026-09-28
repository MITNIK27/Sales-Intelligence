import { ArrowDown, ArrowUp, Building2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPost } from "@/api/client";
import type { CompanyList, CompanySortField, ScrapeAllStarted, SortDirection } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import {
  EnrichmentStatusBadge,
  NeedsReviewBadge,
  QualificationVerdictBadge,
} from "@/components/StatusBadge";
import { TablePagination } from "@/components/TablePagination";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// After a bulk scrape is triggered, refresh the list on an interval for a short window so
// status badges update without a manual page reload — there's no single job to poll here.
const REFRESH_INTERVAL_MS = 3000;
const REFRESH_WINDOW_MS = 60000;

const SORT_LABELS: Record<CompanySortField, string> = {
  name: "Name",
  created_at: "Discovered",
  last_enriched_at: "Last enriched",
  enrichment_status: "Enrichment",
  qualification: "Qualification",
};

export function CompaniesListPage() {
  const [data, setData] = useState<CompanyList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scraping, setScraping] = useState(false);
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sortBy, setSortBy] = useState<CompanySortField>("name");
  const [sortDir, setSortDir] = useState<SortDirection>("asc");
  const refreshRef = useRef<number | null>(null);

  function loadCompanies() {
    setError(null);
    const params = new URLSearchParams({
      limit: String(pageSize),
      offset: String((page - 1) * pageSize),
      sort_by: sortBy,
      sort_dir: sortDir,
    });
    return apiGet<CompanyList>(`/companies?${params}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load companies"));
  }

  useEffect(() => {
    loadCompanies();
    return () => {
      if (refreshRef.current) window.clearInterval(refreshRef.current);
    };
  }, [page, pageSize, sortBy, sortDir]);

  function handleSort(field: CompanySortField) {
    if (field === sortBy) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortDir("asc");
    }
    setPage(1);
  }

  function SortableHead({ field }: { field: CompanySortField }) {
    const active = field === sortBy;
    return (
      <TableHead>
        <button
          type="button"
          onClick={() => handleSort(field)}
          className="flex items-center gap-1 hover:text-foreground"
        >
          {SORT_LABELS[field]}
          {active &&
            (sortDir === "asc" ? (
              <ArrowUp className="size-3.5" />
            ) : (
              <ArrowDown className="size-3.5" />
            ))}
        </button>
      </TableHead>
    );
  }

  async function handleScrapeAll() {
    setScraping(true);
    setScrapeMessage(null);
    try {
      const started = await apiPost<ScrapeAllStarted>("/enrichment/scrape-all");
      setScrapeMessage(
        started.enqueued_count === 0
          ? "Nothing to scrape — every company has already been enriched or is in progress."
          : `Enqueued ${started.enqueued_count} scrape job(s).`,
      );
      if (started.enqueued_count > 0) {
        if (refreshRef.current) window.clearInterval(refreshRef.current);
        refreshRef.current = window.setInterval(loadCompanies, REFRESH_INTERVAL_MS);
        window.setTimeout(() => {
          if (refreshRef.current) window.clearInterval(refreshRef.current);
        }, REFRESH_WINDOW_MS);
      }
    } catch (err) {
      setScrapeMessage(err instanceof Error ? err.message : "failed to start bulk scrape");
    } finally {
      setScraping(false);
    }
  }

  const scrapeAction = (
    <Button type="button" onClick={handleScrapeAll} disabled={scraping || !data}>
      {scraping ? "Starting…" : "Scrape all un-enriched"}
    </Button>
  );

  if (error) {
    return (
      <div>
        <PageHeader eyebrow="Companies" title="Companies" action={scrapeAction} />
        <Card>
          <ErrorState message={error} onRetry={loadCompanies} />
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        <PageHeader eyebrow="Companies" title="Companies" action={scrapeAction} />
        <Card className="p-6">
          <SkeletonLines lines={6} />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader eyebrow="Companies" title={`Companies (${data.total})`} action={scrapeAction} />
      {scrapeMessage && <p className="mb-4 text-sm text-muted-foreground">{scrapeMessage}</p>}

      <Card className="p-0">
        {data.total === 0 ? (
          <EmptyState
            icon={Building2}
            title="No companies yet"
            description="Describe a target market on the Market Discovery page and the system finds, qualifies, and drafts outreach for matching companies automatically — or upload a CSV if you already have a list."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Button asChild>
                  <Link to="/market-discovery">Start Market Discovery</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link to="/upload">Upload a CSV</Link>
                </Button>
              </div>
            }
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHead field="name" />
                  <TableHead>Domain</TableHead>
                  <TableHead>Industry</TableHead>
                  <TableHead>Contacts</TableHead>
                  <SortableHead field="created_at" />
                  <SortableHead field="last_enriched_at" />
                  <SortableHead field="enrichment_status" />
                  <SortableHead field="qualification" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((company) => (
                  <TableRow key={company.id}>
                    <TableCell className="whitespace-normal">
                      <Link to={`/companies/${company.id}`} className="text-primary-text hover:underline">
                        {company.name}
                      </Link>
                    </TableCell>
                    <TableCell>{company.domain ?? "—"}</TableCell>
                    <TableCell>{company.industry ?? "—"}</TableCell>
                    <TableCell>{company.contact_count}</TableCell>
                    <TableCell>{new Date(company.created_at).toLocaleDateString()}</TableCell>
                    <TableCell>
                      {company.last_enriched_at
                        ? new Date(company.last_enriched_at).toLocaleDateString()
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <EnrichmentStatusBadge status={company.enrichment_status} />
                        {company.needs_review && <NeedsReviewBadge />}
                      </div>
                    </TableCell>
                    <TableCell>
                      {company.qualification_verdict ? (
                        <QualificationVerdictBadge verdict={company.qualification_verdict} />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <TablePagination
              total={data.total}
              page={page}
              pageSize={pageSize}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
          </>
        )}
      </Card>
    </div>
  );
}
