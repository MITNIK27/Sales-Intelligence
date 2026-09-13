import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet } from "@/api/client";
import type { NeedsReviewItem } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { TablePagination } from "@/components/TablePagination";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function NeedsReviewPage() {
  const [items, setItems] = useState<NeedsReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

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
  }, []);

  const header = (
    <PageHeader
      eyebrow="Enrichment"
      title="Needs Review"
      description="Scraped companies and contacts with a low-confidence match — spot-check these, nothing here is blocking the pipeline."
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
