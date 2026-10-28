import { Check, ExternalLink, ShieldCheck, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiDelete, apiGet, apiPost } from "@/api/client";
import type {
  BulkConfirmRequest,
  BulkConfirmStarted,
  JobStatus,
  NeedsReviewItem,
  Product,
  ProductList,
} from "@/api/types";
import { Checkbox } from "@/components/Checkbox";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { ProductMultiSelect } from "@/components/ProductMultiSelect";
import { SkeletonLines } from "@/components/Skeleton";
import { WebsiteLink } from "@/components/WebsiteLink";
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
import {
  companyKey,
  contactKey,
  groupByCompany,
  groupKeys,
  pruneSelection,
  selectionState,
  splitSelection,
  toggleKeys,
  type ReviewGroup,
} from "@/features/enrichment/reviewGroups";
import { formatDate, plural } from "@/lib/format";
import {
  explainNeedsReviewReason,
  shortNeedsReviewReason,
} from "@/lib/needsReview";

const POLL_INTERVAL_MS = 1500;

// The reason almost every flagged person has; anything else is shown as a marker on the row.
const USUAL_REASON = "found via contact search, not confirmed";

type Notice = { kind: "info" | "error"; text: string };

// Everything the system found on its own that a person has not yet vouched for, grouped by
// company: pick the people that are right and confirm them, discard the ones that are not.
// Drafting for a person stays paused until they are confirmed here.
export function NeedsReviewPage() {
  const [items, setItems] = useState<NeedsReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [products, setProducts] = useState<Product[] | null>(null);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingDiscard, setPendingDiscard] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmJob, setConfirmJob] = useState<JobStatus | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const pollRef = useRef<number | null>(null);

  const loadItems = useCallback(() => {
    setError(null);
    return apiGet<NeedsReviewItem[]>("/enrichment/needs-review")
      .then((list) => {
        setItems(list);
        setSelected((current) => pruneSelection(current, groupByCompany(list)));
      })
      .catch((err) =>
        setError(
          err instanceof Error
            ? err.message
            : "failed to load the contacts to verify",
        ),
      );
  }, []);

  useEffect(() => {
    void loadItems();
    apiGet<ProductList>("/products")
      .then((list) => {
        setProducts(list.items);
        if (list.items.length === 1) setSelectedProductIds([list.items[0].id]);
      })
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, [loadItems]);

  const groups = useMemo(() => groupByCompany(items ?? []), [items]);
  const allKeys = useMemo(() => groups.flatMap(groupKeys), [groups]);
  const picked = useMemo(() => splitSelection(selected), [selected]);
  const jobRunning =
    confirmJob != null &&
    confirmJob.status !== "done" &&
    confirmJob.status !== "failed";
  const disabled = busy || jobRunning;

  // Confirming through the bulk job is what resumes role classification and drafting for a
  // confirmed company; it also clears the flag on the chosen people.
  async function confirmIds(companyIds: string[], contactIds: string[]) {
    if (companyIds.length === 0 && contactIds.length === 0) return;
    setBusy(true);
    setNotice(null);
    setConfirmJob(null);
    try {
      const body: BulkConfirmRequest = {
        company_ids: companyIds,
        contact_ids: contactIds,
        product_ids: selectedProductIds,
      };
      const started = await apiPost<BulkConfirmStarted>(
        "/enrichment/needs-review/confirm-bulk",
        body,
      );
      pollRef.current = window.setInterval(async () => {
        try {
          const status = await apiGet<JobStatus>(`/jobs/${started.job_id}`);
          setConfirmJob(status);
          if (status.status === "done" || status.status === "failed") {
            if (pollRef.current !== null) window.clearInterval(pollRef.current);
            await loadItems();
          }
        } catch {
          if (pollRef.current !== null) window.clearInterval(pollRef.current);
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setNotice({
        kind: "error",
        text: err instanceof Error ? err.message : "failed to confirm",
      });
    } finally {
      setBusy(false);
    }
  }

  // One person on one row: no job needed, so it is instant.
  async function confirmOne(contactId: string) {
    setBusy(true);
    setNotice(null);
    try {
      await apiPost(`/contacts/${contactId}/confirm`);
      await loadItems();
    } catch (err) {
      setNotice({
        kind: "error",
        text:
          err instanceof Error ? err.message : "failed to confirm the contact",
      });
    } finally {
      setBusy(false);
    }
  }

  async function discard(contactIds: string[]) {
    setBusy(true);
    setNotice(null);
    setPendingDiscard(null);
    let failed = 0;
    let lastError = "";
    for (const id of contactIds) {
      try {
        await apiDelete(`/contacts/${id}`);
      } catch (err) {
        failed += 1;
        lastError = err instanceof Error ? err.message : "failed";
      }
    }
    await loadItems();
    const done = contactIds.length - failed;
    setNotice(
      failed === 0
        ? {
            kind: "info",
            text: `Discarded ${done} ${plural(done, "contact")}.`,
          }
        : {
            kind: "error",
            text: `Discarded ${done}, could not discard ${failed}: ${lastError}`,
          },
    );
    setBusy(false);
  }

  const header = (
    <PageHeader
      title="Verify Contacts"
      description="People we found on the web, grouped by company. Confirm the right ones; discard the rest. Drafts for a person wait until you confirm them."
    />
  );

  if (error) {
    return (
      <div>
        {header}
        <Card>
          <ErrorState message={error} onRetry={() => void loadItems()} />
        </Card>
      </div>
    );
  }

  if (!items) {
    return (
      <div>
        {header}
        <Card className="p-6">
          <SkeletonLines lines={6} />
        </Card>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div>
        {header}
        {jobRunning || confirmJob ? <JobNote job={confirmJob} /> : null}
        <Card className="p-0">
          <EmptyState
            icon={ShieldCheck}
            title="Nothing to verify"
            description="When a search finds people we are not sure about, they appear here for a quick check."
          />
        </Card>
      </div>
    );
  }

  const pageCount = Math.max(1, Math.ceil(groups.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visible = groups.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );
  const masterState = selectionState(selected, allKeys);
  const selectedCount = selected.size;

  return (
    <div className="flex flex-col gap-4">
      {header}

      <div className="sticky top-0 z-10 flex flex-col gap-3 border border-border bg-card px-5 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 text-sm">
            <Checkbox
              checked={masterState === "all"}
              indeterminate={masterState === "some"}
              onChange={() => setSelected(toggleKeys(selected, allKeys))}
              label="Select everything"
            />
            <span>
              {selectedCount > 0 ? (
                <strong>{selectedCount} selected</strong>
              ) : (
                <span className="text-muted-foreground">
                  {items.length} to verify across {groups.length}{" "}
                  {plural(groups.length, "company", "companies")}
                </span>
              )}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {products && products.length > 1 && (
              <ProductMultiSelect
                products={products}
                selectedIds={new Set(selectedProductIds)}
                onToggle={(productId) =>
                  setSelectedProductIds((current) =>
                    current.includes(productId)
                      ? current.filter((id) => id !== productId)
                      : [...current, productId],
                  )
                }
              />
            )}
            <Button
              type="button"
              disabled={disabled || selectedCount === 0}
              onClick={() =>
                void confirmIds(picked.companyIds, picked.contactIds)
              }
            >
              <Check className="size-4" /> Confirm
              {selectedCount > 0 ? ` (${selectedCount})` : ""}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={disabled || picked.contactIds.length === 0}
              title={
                picked.contactIds.length === 0 && selectedCount > 0
                  ? "Only people can be discarded here"
                  : undefined
              }
              onClick={() => setPendingDiscard(picked.contactIds)}
            >
              <Trash2 className="size-4" /> Discard
              {picked.contactIds.length > 0
                ? ` (${picked.contactIds.length})`
                : ""}
            </Button>
          </div>
        </div>

        {pendingDiscard && (
          <div
            role="alertdialog"
            aria-label="Confirm discard"
            className="flex flex-wrap items-center justify-between gap-3 border border-destructive/40 bg-chip-rejected-bg px-4 py-3 text-sm"
          >
            <span>
              Discard {pendingDiscard.length}{" "}
              {plural(pendingDiscard.length, "contact")}? They are removed
              permanently.
            </span>
            <span className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => void discard(pendingDiscard)}
              >
                Yes, discard
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setPendingDiscard(null)}
              >
                Cancel
              </Button>
            </span>
          </div>
        )}
      </div>

      <div aria-live="polite" className="flex flex-col gap-2">
        {notice && (
          <p
            className={
              notice.kind === "error" ? "text-sm text-destructive" : "text-sm"
            }
          >
            {notice.text}
          </p>
        )}
        {confirmJob && <JobNote job={confirmJob} />}
      </div>

      <div className="flex flex-col gap-4">
        {visible.map((group) => (
          <GroupCard
            key={group.companyId}
            group={group}
            selected={selected}
            disabled={disabled}
            onToggle={(keys) => setSelected(toggleKeys(selected, keys))}
            onConfirmContact={(id) => void confirmOne(id)}
            onConfirmCompany={(id) => void confirmIds([id], [])}
            onDiscardContact={(id) => setPendingDiscard([id])}
          />
        ))}
      </div>

      <Card className="p-0">
        <TablePagination
          total={groups.length}
          page={currentPage}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      </Card>
    </div>
  );
}

function JobNote({ job }: { job: JobStatus | null }) {
  if (!job) return null;
  return (
    <p
      className={
        job.status === "failed" ? "text-sm text-destructive" : "text-sm"
      }
    >
      {job.status === "failed"
        ? job.error
        : job.status === "done"
          ? "Confirmed. Role classification and drafting have resumed where a product was chosen."
          : job.progress
            ? `Confirming ${job.progress.done} of ${job.progress.total}…`
            : "Confirming…"}
    </p>
  );
}

// One company: its flagged people in a table, a master checkbox for the whole company, and the
// company's own flag (if any) on a line above.
function GroupCard({
  group,
  selected,
  disabled,
  onToggle,
  onConfirmContact,
  onConfirmCompany,
  onDiscardContact,
}: {
  group: ReviewGroup;
  selected: ReadonlySet<string>;
  disabled: boolean;
  onToggle: (keys: string[]) => void;
  onConfirmContact: (contactId: string) => void;
  onConfirmCompany: (companyId: string) => void;
  onDiscardContact: (contactId: string) => void;
}) {
  const keys = groupKeys(group);
  const state = selectionState(selected, keys);
  const count = group.contacts.length;
  return (
    <Card className="gap-0 overflow-hidden p-0">
      <div className="flex items-center gap-3 bg-sidebar px-5 py-3 text-white">
        <Checkbox
          checked={state === "all"}
          indeterminate={state === "some"}
          onChange={() => onToggle(keys)}
          label={`Select everything for ${group.companyName}`}
        />
        <Link
          to={`/companies/${group.companyId}`}
          className="text-base font-semibold hover:underline focus-visible:outline-2 focus-visible:outline-white"
        >
          {group.companyName}
        </Link>
        <span className="text-sm text-white/70">
          {count} {plural(count, "contact")}
        </span>
        {group.companyDomain && (
          <WebsiteLink
            domain={group.companyDomain}
            light
            className="ml-auto text-sm"
          />
        )}
      </div>

      {group.companyFlag && (
        <div className="flex flex-wrap items-center gap-3 border-b border-border bg-chip-warning-bg/50 px-5 py-3 text-sm">
          <Checkbox
            checked={selected.has(companyKey(group.companyId))}
            onChange={() => onToggle([companyKey(group.companyId)])}
            label={`Select ${group.companyName} company details`}
          />
          <span
            className="flex-1"
            title={explainNeedsReviewReason(group.companyFlag.reason) ?? ""}
          >
            <strong>Company details not verified</strong> ·{" "}
            {shortNeedsReviewReason(group.companyFlag.reason)} ·{" "}
            <span className="text-muted-foreground">
              {formatDate(group.companyFlag.flagged_at)}
            </span>
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={disabled}
            onClick={() => onConfirmCompany(group.companyId)}
          >
            <Check className="size-4" /> Confirm company
          </Button>
        </div>
      )}

      {count > 0 && (
        <div className="overflow-x-auto">
          <Table className="min-w-[720px] table-fixed">
            <colgroup>
              <col className="w-14" />
              <col />
              <col className="w-48" />
              <col className="w-32" />
              <col className="w-56" />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead>
                  <span className="sr-only">Select</span>
                </TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Details</TableHead>
                <TableHead>Found</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>{" "}
            <TableBody>
              {group.contacts.map((item) => {
                const id = item.contact_id as string;
                return (
                  <TableRow key={id}>
                    <TableCell className="pl-5">
                      <Checkbox
                        checked={selected.has(contactKey(id))}
                        onChange={() => onToggle([contactKey(id)])}
                        label={`Select ${item.contact_name ?? "contact"}`}
                      />
                    </TableCell>
                    <TableCell
                      className="whitespace-normal"
                      title={explainNeedsReviewReason(item.reason) ?? ""}
                    >
                      <p className="flex flex-wrap items-center gap-2 font-medium">
                        {item.contact_name ?? "Unnamed contact"}
                        {/* The usual "found by web search" is true of nearly every row, so only
                            an unusual reason (e.g. low confidence) is worth a marker. */}
                        {item.reason !== USUAL_REASON && (
                          <span className="bg-chip-warning-bg px-1.5 py-0.5 text-xs font-medium text-chip-warning-fg">
                            {shortNeedsReviewReason(item.reason)}
                          </span>
                        )}
                      </p>
                      {item.contact_title && (
                        <p className="text-xs text-muted-foreground">
                          {item.contact_title}
                        </p>
                      )}
                    </TableCell>
                    <TableCell className="whitespace-normal text-sm">
                      <p
                        className={
                          item.contact_email ? "" : "text-muted-foreground"
                        }
                      >
                        {item.contact_email ?? "No email"}
                      </p>
                      {item.contact_linkedin && (
                        <a
                          href={item.contact_linkedin}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-primary-text hover:underline"
                        >
                          LinkedIn{" "}
                          <ExternalLink className="size-3" aria-hidden="true" />
                        </a>
                      )}
                    </TableCell>
                    <TableCell className="text-sm tabular-nums text-muted-foreground">
                      {formatDate(item.flagged_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={disabled}
                          onClick={() => onConfirmContact(id)}
                        >
                          <Check className="size-4" /> Confirm
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          disabled={disabled}
                          onClick={() => onDiscardContact(id)}
                        >
                          <Trash2 className="size-4" /> Discard
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  );
}
