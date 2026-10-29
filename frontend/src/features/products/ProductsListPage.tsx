import { ChevronDown, Package } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiDelete, apiGet } from "@/api/client";
import type {
  OfferingProposalList,
  Product,
  ProductKind,
  ProductList,
} from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { InfoTip } from "@/components/InfoTip";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { TablePagination } from "@/components/TablePagination";
import { Badge } from "@/components/ui/badge";
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
import { WebsiteLink } from "@/components/WebsiteLink";
import { CoveragePanel } from "@/features/products/CoveragePanel";
import { ProposalReview } from "@/features/products/ProposalReview";
import { failureLabel, lastCheckedLabel, progressLabel } from "@/features/products/proposals";
import { useOfferingSync } from "@/features/products/useOfferingSync";
import { usePersistentState } from "@/lib/usePersistentState";
import {
  KIND_LABEL,
  KIND_LABEL_PLURAL,
  KIND_ORDER,
  OFFERINGS_LABEL,
  OFFERINGS_TAGLINE,
  countByKind,
  kindOf,
} from "@/lib/offerings";
import { cn } from "@/lib/utils";

export function ProductsListPage() {
  const [data, setData] = useState<ProductList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [kind, setKind] = usePersistentState<ProductKind>("ui.offerings.tab", "service");
  const [proposals, setProposals] = useState<OfferingProposalList | null>(null);
  const [showCoverage, setShowCoverage] = usePersistentState<boolean>("ui.offerings.coverage", false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  function loadProducts() {
    setError(null);
    return apiGet<ProductList>("/products?limit=200")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load offerings"));
  }

  // Changes the website check found, waiting for a person. A failure here only hides the panel:
  // the offerings themselves still load and work.
  function loadProposals() {
    return apiGet<OfferingProposalList>("/products/proposals")
      .then(setProposals)
      .catch(() => setProposals(null));
  }

  const sync = useOfferingSync(() => {
    loadProposals();
    loadProducts();
  });

  function reloadAfterDecision() {
    loadProducts();
    loadProposals();
    sync.refresh();
  }

  useEffect(() => {
    loadProducts();
    loadProposals();
  }, []);

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await apiDelete(`/products/${id}`);
      await loadProducts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to delete offering");
    } finally {
      setDeletingId(null);
    }
  }

  const addAction = (
    <Button asChild>
      <Link to="/products/new">Add offering</Link>
    </Button>
  );
  const running = sync.status?.running ?? false;
  const checkAction = (
    <div className="flex items-center gap-3">
      <div className="text-right text-sm text-muted-foreground" aria-live="polite">
        {sync.error ? (
          <span className="text-destructive">{sync.error}</span>
        ) : sync.status ? (
          running ? (
            progressLabel(sync.status)
          ) : sync.status.last_error ? (
            failureLabel(sync.status.last_error)
          ) : (
            lastCheckedLabel(sync.status)
          )
        ) : null}
      </div>
      <Button
        type="button"
        variant="outline"
        disabled={running || sync.status === null}
        onClick={sync.start}
      >
        {running ? "Checking…" : "Check for updates"}
      </Button>
      {addAction}
    </div>
  );
  const header = (
    <PageHeader title={OFFERINGS_LABEL} description={OFFERINGS_TAGLINE} action={checkAction} />
  );

  if (error) {
    return (
      <div>
        {header}
        <Card>
          <ErrorState message={error} onRetry={loadProducts} />
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        {header}
        <Card className="p-6">
          <SkeletonLines lines={6} />
        </Card>
      </div>
    );
  }

  const counts = countByKind(data.items);
  const inTab = data.items.filter((product) => kindOf(product) === kind);
  const pageCount = Math.max(1, Math.ceil(inTab.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const rows = inTab.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  function selectKind(next: ProductKind) {
    setKind(next);
    setPage(1);
  }

  return (
    <div>
      {header}

      {proposals && proposals.items.length > 0 && (
        <ProposalReview proposals={proposals.items} onDecided={reloadAfterDecision} />
      )}

      <div className="mb-4 flex items-end justify-between gap-4 border-b border-border">
        <div role="tablist" aria-label="Offering type" className="flex gap-1">
          {KIND_ORDER.map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={kind === tab}
              onClick={() => selectKind(tab)}
              className={cn(
                "-mb-px border-b-2 px-4 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-primary",
                kind === tab
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {KIND_LABEL_PLURAL[tab]}
              <span className="ml-2 tabular-nums text-muted-foreground">{counts[tab]}</span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 pb-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-expanded={showCoverage}
            onClick={() => setShowCoverage(!showCoverage)}
          >
            What was checked
            <ChevronDown
              className={cn("size-4 transition-transform", showCoverage && "rotate-180")}
              aria-hidden="true"
            />
          </Button>
          <InfoTip label="About what was checked">
            Every page the check looked at, what it decided and why. Open it to see why something
            is missing, or to ask for a page to be read as an offering.
          </InfoTip>
        </div>
      </div>

      {showCoverage && <CoveragePanel onCheckStarted={sync.refresh} onRunCheck={sync.start} />}

      <Card className="p-0">
        {inTab.length === 0 ? (
          <EmptyState
            icon={Package}
            title={`No ${KIND_LABEL_PLURAL[kind].toLowerCase()} yet`}
            description={`Add a ${KIND_LABEL[kind].toLowerCase()} so it can be recommended to companies.`}
            action={
              <Button asChild>
                <Link to="/products/new">Add offering</Link>
              </Button>
            }
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((product) => (
                  <OfferingRow
                    key={product.id}
                    product={product}
                    deleting={deletingId === product.id}
                    onDelete={() => handleDelete(product.id)}
                  />
                ))}
              </TableBody>
            </Table>
            <TablePagination
              total={inTab.length}
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

function OfferingRow({
  product,
  deleting,
  onDelete,
}: {
  product: Product;
  deleting: boolean;
  onDelete: () => void;
}) {
  const fromWebsite = product.source === "website";
  return (
    <TableRow>
      <TableCell className="whitespace-normal font-medium">{product.name}</TableCell>
      <TableCell className="whitespace-normal text-muted-foreground">
        {product.description ?? "—"}
      </TableCell>
      <TableCell className="whitespace-normal">
        <div className="flex flex-col items-start gap-1">
          <Badge variant="outline">{fromWebsite ? "From website" : "Manual"}</Badge>
          {fromWebsite && product.source_url && (
            <WebsiteLink domain={product.source_url} className="text-xs" />
          )}
        </div>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-3">
          <Link
            to={`/products/${product.id}/edit`}
            className="text-sm text-primary-text hover:underline"
          >
            Edit
          </Link>
          {!fromWebsite && (
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={deleting}
              onClick={onDelete}
            >
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}
