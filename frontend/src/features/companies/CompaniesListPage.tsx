import { ArrowDown, ArrowUp, Building2 } from "lucide-react";
import { WebsiteLink } from "@/components/WebsiteLink";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPost } from "@/api/client";
import type {
  CompanyList,
  CompanySortField,
  ScrapeAllStarted,
  SortDirection,
} from "@/api/types";
import { Checkbox } from "@/components/Checkbox";
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
import { Tabs } from "@/components/Tabs";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { restoreCompany } from "@/features/companies/api";
import { errorMessage } from "@/features/companies/lib/contacts";
import { NotAFitButton } from "@/features/companies/notAFit/NotAFitButton";
import { reasonLabel } from "@/features/companies/notAFit/reasons";
import { formatDate } from "@/lib/format";

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

type ListView = "active" | "dismissed";

const LIST_TABS: { id: ListView; label: string }[] = [
  { id: "active", label: "Companies" },
  { id: "dismissed", label: "Not a fit" },
];

export function CompaniesListPage() {
  const { showToast } = useToast();
  const [view, setView] = useState<ListView>("active");
  // Companies ticked on this page, for marking several not a fit at once.
  const [selected, setSelected] = useState<Set<string>>(new Set());
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
    if (view === "dismissed") params.set("dismissed", "only");
    return apiGet<CompanyList>(`/companies?${params}`)
      .then(setData)
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : "failed to load companies",
        ),
      );
  }

  useEffect(() => {
    setSelected(new Set()); // a ticked row that is no longer on screen must not be acted on
    loadCompanies();
    return () => {
      if (refreshRef.current) window.clearInterval(refreshRef.current);
    };
  }, [page, pageSize, sortBy, sortDir, view]);

  function changeView(next: ListView) {
    setView(next);
    setPage(1);
  }

  function toggleOne(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllOnPage() {
    if (!data) return;
    const ids = data.items.map((company) => company.id);
    setSelected((current) =>
      ids.every((id) => current.has(id)) ? new Set() : new Set(ids),
    );
  }

  async function handleRestore(id: string, name: string) {
    try {
      await restoreCompany(id);
      showToast({ description: `${name} restored.`, variant: "success" });
      await loadCompanies();
    } catch (err) {
      showToast({ description: errorMessage(err, "failed to restore the company") });
    }
  }

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
        refreshRef.current = window.setInterval(
          loadCompanies,
          REFRESH_INTERVAL_MS,
        );
        window.setTimeout(() => {
          if (refreshRef.current) window.clearInterval(refreshRef.current);
        }, REFRESH_WINDOW_MS);
      }
    } catch (err) {
      setScrapeMessage(
        err instanceof Error ? err.message : "failed to start bulk scrape",
      );
    } finally {
      setScraping(false);
    }
  }

  const scrapeAction = (
    <Button
      type="button"
      onClick={handleScrapeAll}
      disabled={scraping || !data}
    >
      {scraping ? "Starting…" : "Scrape all un-enriched"}
    </Button>
  );

  if (error) {
    return (
      <div>
        <PageHeader title="Companies" action={scrapeAction} />
        <Card>
          <ErrorState message={error} onRetry={loadCompanies} />
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        <PageHeader title="Companies" action={scrapeAction} />
        <Card className="p-6">
          <SkeletonLines lines={6} />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={`${view === "active" ? "Companies" : "Not a fit"} (${data.total})`}
        action={view === "active" ? scrapeAction : undefined}
      />
      <Tabs
        label="Company lists"
        tabs={LIST_TABS}
        active={view}
        onChange={changeView}
      />
      {view === "active" && scrapeMessage && (
        <p className="mb-4 text-sm text-muted-foreground">{scrapeMessage}</p>
      )}

      <Card className="p-0">
        {data.total === 0 && view === "dismissed" ? (
          <EmptyState
            icon={Building2}
            title="Nothing marked not a fit"
            description="Companies you mark as not a fit are listed here, where you can undo it. Every reason you give helps us see what the search gets wrong."
          />
        ) : data.total === 0 ? (
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
            {view === "active" && selected.size > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 text-sm">
                <span>{selected.size} selected</span>
                <div className="flex items-center gap-2">
                  <NotAFitButton
                    companyIds={[...selected]}
                    label={`Not a fit (${selected.size})`}
                    onDone={() => {
                      setSelected(new Set());
                      void loadCompanies();
                    }}
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setSelected(new Set())}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  {view === "active" && (
                    <TableHead className="w-8">
                      <Checkbox
                        checked={
                          data.items.length > 0 &&
                          data.items.every((company) => selected.has(company.id))
                        }
                        indeterminate={selected.size > 0}
                        onChange={toggleAllOnPage}
                        label="Select all companies on this page"
                      />
                    </TableHead>
                  )}
                  <SortableHead field="name" />
                  <TableHead>Website</TableHead>
                  <TableHead>Industry</TableHead>
                  <TableHead>Contacts</TableHead>
                  <SortableHead field="created_at" />
                  <SortableHead field="last_enriched_at" />
                  <SortableHead field="enrichment_status" />
                  <SortableHead field="qualification" />
                  {view === "dismissed" && (
                    <>
                      <TableHead>Reason</TableHead>
                      <TableHead />
                    </>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((company) => (
                  <TableRow key={company.id}>
                    {view === "active" && (
                      <TableCell>
                        <Checkbox
                          checked={selected.has(company.id)}
                          onChange={() => toggleOne(company.id)}
                          label={`Select ${company.name}`}
                        />
                      </TableCell>
                    )}
                    <TableCell className="whitespace-normal">
                      <Link
                        to={`/companies/${company.id}`}
                        className="text-primary-text hover:underline"
                      >
                        {company.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {company.domain ? (
                        <WebsiteLink domain={company.domain} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>{company.industry ?? "—"}</TableCell>
                    <TableCell>{company.contact_count}</TableCell>
                    <TableCell>{formatDate(company.created_at)}</TableCell>
                    <TableCell>
                      {company.last_enriched_at
                        ? formatDate(company.last_enriched_at)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <EnrichmentStatusBadge
                          status={company.enrichment_status}
                        />
                        {company.needs_review && <NeedsReviewBadge />}
                      </div>
                    </TableCell>
                    <TableCell>
                      {company.qualification_verdict ? (
                        <QualificationVerdictBadge
                          verdict={company.qualification_verdict}
                        />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    {view === "dismissed" && (
                      <>
                        <TableCell className="whitespace-normal">
                          {reasonLabel(company.dismissed_reason)}
                        </TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => handleRestore(company.id, company.name)}
                          >
                            Undo
                          </Button>
                        </TableCell>
                      </>
                    )}
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
