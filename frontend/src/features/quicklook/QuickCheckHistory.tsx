import { ChevronDown, History, Loader2, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { StatusTag } from "@/components/StatusTag";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  checkedCompanies,
  companyChecks,
  type CheckedCompany,
  type CheckEntry,
} from "@/features/quicklook/api";
import { CALL_SHORT, CALL_TONE } from "@/features/quicklook/callStyle";
import { formatDateTime, plural, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE = 20;

// The companies this person looked up before, newest first. Opening one lists each check (when, the
// focus and criteria asked about, and the call it got then); "View answer" shows that answer
// exactly as it was given.
export function QuickCheckHistory({
  version,
  openEntryId,
  onOpen,
}: {
  // Changes after every new look-up, so the list picks it up.
  version: number;
  // The earlier answer on screen, marked in the list.
  openEntryId: string | null;
  onOpen: (entryId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<CheckedCompany[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(
      () => {
        checkedCompanies(query, 0, PAGE)
          .then((list) => {
            if (cancelled) return;
            setItems(list.items);
            setTotal(list.total);
            setError(null);
          })
          .catch(() => {
            if (!cancelled)
              setError("Your earlier checks could not be loaded.");
          });
      },
      query ? 250 : 0,
    );
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, version]);

  async function more() {
    if (!items) return;
    setLoadingMore(true);
    try {
      const list = await checkedCompanies(query, items.length, PAGE);
      setItems([...items, ...list.items]);
      setTotal(list.total);
    } catch {
      setError("More checks could not be loaded.");
    } finally {
      setLoadingMore(false);
    }
  }

  const searching = query.trim() !== "";
  if (items !== null && items.length === 0 && !searching && !error)
    return (
      <section className="mt-8 border border-dashed border-border px-5 py-6 text-center text-sm text-muted-foreground">
        <History className="mx-auto mb-2 size-5" aria-hidden="true" />
        Companies you check appear here, so you can go back to them.
      </section>
    );

  return (
    <section
      aria-labelledby="earlier-checks"
      className="mt-8 border border-border bg-card shadow-xs"
    >
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-4">
        <History className="size-5 text-primary" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h2 id="earlier-checks" className="text-lg font-bold leading-tight">
            Your earlier checks
          </h2>
          <p className="text-sm text-muted-foreground">
            {items === null
              ? "Loading…"
              : `${total} ${plural(total, "company", "companies")}${searching ? " found" : ""}. Only you see these.`}
          </p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a company"
            aria-label="Find a company in your earlier checks"
            maxLength={200}
            className="pl-8"
          />
        </div>
      </header>

      {error && (
        <p role="alert" className="px-5 py-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {items !== null && items.length === 0 && searching && (
        <p className="px-5 py-6 text-sm text-muted-foreground">
          None of your checks match &ldquo;{query.trim()}&rdquo;.
        </p>
      )}

      {items !== null && items.length > 0 && (
        <ul className="divide-y divide-border">
          {items.map((company) => (
            <CompanyRow
              key={company.domain}
              company={company}
              version={version}
              openEntryId={openEntryId}
              onOpen={onOpen}
            />
          ))}
        </ul>
      )}

      {items !== null && items.length < total && (
        <div className="border-t border-border px-5 py-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void more()}
            disabled={loadingMore}
          >
            {loadingMore && (
              <Loader2 className="animate-spin" aria-hidden="true" />
            )}
            Show more
          </Button>
        </div>
      )}
    </section>
  );
}

function CompanyRow({
  company,
  version,
  openEntryId,
  onOpen,
}: {
  company: CheckedCompany;
  version: number;
  openEntryId: string | null;
  onOpen: (entryId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<CheckEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const panelId = `checks-${company.domain}`;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    companyChecks(company.domain)
      .then((result) => {
        if (!cancelled) {
          setEntries(result.entries);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("These checks could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [open, company.domain, company.checks, version]);

  return (
    <li>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls={panelId}
          className="group flex min-w-0 flex-1 items-center gap-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <ChevronDown
            className={cn(
              "size-4 shrink-0 text-muted-foreground transition-transform duration-150 motion-reduce:transition-none",
              open && "rotate-180",
            )}
            aria-hidden="true"
          />
          <span className="min-w-0">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-semibold group-hover:underline group-hover:underline-offset-4">
                {company.name}
              </span>
              <span className="text-sm text-muted-foreground">
                {company.domain}
              </span>
            </span>
            <span className="block text-xs text-muted-foreground">
              {company.checks === 1
                ? `Checked ${timeAgo(company.last_checked_at)}`
                : `Checked ${company.checks} times, last ${timeAgo(company.last_checked_at)}`}
              {company.last_focus ? ` · Focus: ${company.last_focus}` : ""}
            </span>
          </span>
        </button>
        <StatusTag tone={CALL_TONE[company.last_call]}>
          {CALL_SHORT[company.last_call]}
        </StatusTag>
        {company.existing_company_id && (
          <Link
            to={`/companies/${company.existing_company_id}`}
            className="text-sm font-medium text-primary-text underline-offset-4 hover:underline"
          >
            In your companies
          </Link>
        )}
      </div>

      {open && (
        <div
          id={panelId}
          className="border-t border-border bg-muted/40 px-5 py-3"
        >
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!entries && !error && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Loading checks…
            </p>
          )}
          {entries && (
            <ol className="flex flex-col gap-3">
              {entries.map((entry) => (
                <li
                  key={entry.id}
                  className={cn(
                    "flex flex-wrap items-start gap-x-4 gap-y-1 border-l-2 pl-3",
                    entry.id === openEntryId
                      ? "border-primary"
                      : "border-border",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-x-3 text-sm">
                      <span className="font-medium">
                        {formatDateTime(entry.checked_at)}
                      </span>
                      <StatusTag tone={CALL_TONE[entry.call]}>
                        {CALL_SHORT[entry.call]}
                      </StatusTag>
                      {entry.refreshed && (
                        <span className="text-xs text-muted-foreground">
                          Refreshed
                        </span>
                      )}
                      {entry.cached && (
                        <span className="text-xs text-muted-foreground">
                          Saved answer shown
                        </span>
                      )}
                    </p>
                    {(entry.focus || entry.criteria.length > 0) && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {entry.focus && `Focus: ${entry.focus}`}
                        {entry.focus && entry.criteria.length > 0 && " · "}
                        {entry.criteria.length > 0 &&
                          `Your criteria: ${entry.criteria.join("; ")}`}
                      </p>
                    )}
                    {entry.call_reason && (
                      <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
                        {entry.call_reason}
                      </p>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onOpen(entry.id)}
                  >
                    {entry.id === openEntryId ? "Showing above" : "View answer"}
                  </Button>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}
