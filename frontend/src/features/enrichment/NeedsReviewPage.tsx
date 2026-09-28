import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPost } from "@/api/client";
import type {
  BulkConfirmRequest,
  BulkConfirmStarted,
  JobStatus,
  NeedsReviewItem,
  Product,
  ProductList,
} from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { TablePagination } from "@/components/TablePagination";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const POLL_INTERVAL_MS = 1500;

export function NeedsReviewPage() {
  const [items, setItems] = useState<NeedsReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const [products, setProducts] = useState<Product[] | null>(null);
  const [selectedProductId, setSelectedProductId] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [confirmJob, setConfirmJob] = useState<JobStatus | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  function loadItems() {
    setError(null);
    return apiGet<NeedsReviewItem[]>("/enrichment/needs-review")
      .then(setItems)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "failed to load needs-review items"),
      );
  }

  useEffect(() => {
    loadItems();
    apiGet<ProductList>("/products")
      .then((list) => {
        setProducts(list.items);
        if (list.items.length === 1) setSelectedProductId(list.items[0].id);
      })
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
  }, []);

  async function handleConfirmAll() {
    if (!items || items.length === 0) return;
    setConfirming(true);
    setConfirmError(null);
    setConfirmJob(null);
    try {
      const companyIds = Array.from(
        new Set(items.filter((i) => i.entity_type === "company").map((i) => i.company_id)),
      );
      const contactIds = Array.from(
        new Set(
          items
            .filter((i) => i.entity_type === "contact" && i.contact_id)
            .map((i) => i.contact_id as string),
        ),
      );
      const body: BulkConfirmRequest = {
        company_ids: companyIds,
        contact_ids: contactIds,
        product_id: selectedProductId || null,
      };
      const started = await apiPost<BulkConfirmStarted>(
        "/enrichment/needs-review/confirm-bulk",
        body,
      );
      const poll = window.setInterval(async () => {
        const status = await apiGet<JobStatus>(`/jobs/${started.job_id}`);
        setConfirmJob(status);
        if (status.status === "done" || status.status === "failed") {
          window.clearInterval(poll);
          await loadItems();
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : "failed to confirm items");
    } finally {
      setConfirming(false);
    }
  }

  const action =
    items && items.length > 0 ? (
      <div className="flex flex-wrap items-center gap-2">
        {products && products.length > 1 && (
          <Select value={selectedProductId} onValueChange={setSelectedProductId}>
            <SelectTrigger className="h-9 min-w-40 bg-card" aria-label="Product">
              <SelectValue placeholder="Product for drafting…" />
            </SelectTrigger>
            <SelectContent>
              {products.map((product) => (
                <SelectItem key={product.id} value={product.id}>
                  {product.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Button
          type="button"
          onClick={handleConfirmAll}
          disabled={confirming || (confirmJob != null && confirmJob.status !== "done" && confirmJob.status !== "failed")}
        >
          {confirming ? "Starting…" : `Confirm all (${items.length})`}
        </Button>
      </div>
    ) : undefined;

  const header = (
    <PageHeader
      eyebrow="Enrichment"
      title="Needs Review"
      description="Companies and contacts the pipeline isn't confident about — role classification and drafting are paused for each one until it's confirmed here, one at a time on its own page or all at once with the action above."
      action={action}
    />
  );

  if (error) {
    return (
      <div>
        {header}
        <Card>
          <ErrorState message={error} onRetry={loadItems} />
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

  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const rows = items.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <div>
      {header}
      {confirmError && <p className="mb-4 text-sm text-destructive">{confirmError}</p>}
      {confirmJob && (
        <Card className="mb-4">
          <div className="p-4 text-sm">
            {confirmJob.status === "running" && confirmJob.progress && (
              <p className="text-muted-foreground">
                Confirming {confirmJob.progress.done} of {confirmJob.progress.total}…
              </p>
            )}
            {confirmJob.status === "failed" && (
              <p className="text-destructive">{confirmJob.error}</p>
            )}
            {confirmJob.status === "done" && (
              <p className="text-muted-foreground">
                Confirmed — role classification and drafting have resumed for confirmed
                companies where a product was selected.
              </p>
            )}
          </div>
        </Card>
      )}
      <Card className="p-0">
        {items.length === 0 ? (
          <EmptyState
            icon={Search}
            title="Nothing flagged right now"
            description="Low-confidence matches from scraping will show up here for a spot-check."
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Flagged</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((item) => (
                  <TableRow key={`${item.entity_type}-${item.company_id}-${item.contact_id ?? ""}`}>
                    <TableCell className="capitalize">{item.entity_type}</TableCell>
                    <TableCell>
                      <Link
                        to={`/companies/${item.company_id}`}
                        className="text-primary-text hover:underline"
                      >
                        {item.company_name}
                      </Link>
                    </TableCell>
                    <TableCell>{item.contact_name ?? "—"}</TableCell>
                    <TableCell className="whitespace-normal">{item.reason}</TableCell>
                    <TableCell>{new Date(item.flagged_at).toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <TablePagination
              total={items.length}
              page={currentPage}
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
