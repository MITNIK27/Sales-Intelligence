import { ListChecks } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet } from "@/api/client";
import type { FollowUpItem } from "@/api/types";
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

export function FollowUpsPage() {
  const [items, setItems] = useState<FollowUpItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  function loadFollowUps() {
    setError(null);
    return apiGet<FollowUpItem[]>("/contacts/follow-ups")
      .then(setItems)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load follow-ups"));
  }

  useEffect(() => {
    loadFollowUps();
  }, []);

  const header = (
    <PageHeader
      eyebrow="Contacts"
      title="Follow-ups Due"
      description="Contacts whose next follow-up date is today or in the past."
    />
  );

  if (error) {
    return (
      <div>
        {header}
        <Card>
          <ErrorState message={error} onRetry={loadFollowUps} />
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
            icon={ListChecks}
            title="Nothing due right now"
            description="Contacts will show up here once a follow-up date arrives."
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Contact</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead>Channel</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="whitespace-normal">
                      {item.full_name ?? "Unknown"}
                      {item.role_title && ` (${item.role_title})`}
                    </TableCell>
                    <TableCell>
                      <Link
                        to={`/companies/${item.company.id}`}
                        className="text-primary-text hover:underline"
                      >
                        {item.company.name}
                      </Link>
                    </TableCell>
                    <TableCell className="capitalize">{item.status.replace(/_/g, " ")}</TableCell>
                    <TableCell>
                      {item.next_follow_up_at
                        ? new Date(item.next_follow_up_at).toLocaleDateString()
                        : "—"}
                    </TableCell>
                    <TableCell className="capitalize">
                      {item.next_follow_up_channel ?? "—"}
                    </TableCell>
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
