import { ClipboardCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiDelete, apiGet } from "@/api/client";
import type { QualificationCriterionList } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
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

export function CriteriaListPage() {
  const [data, setData] = useState<QualificationCriterionList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  function loadCriteria() {
    setError(null);
    return apiGet<QualificationCriterionList>("/qualification/criteria")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load criteria"));
  }

  useEffect(() => {
    loadCriteria();
  }, []);

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await apiDelete(`/qualification/criteria/${id}`);
      await loadCriteria();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to delete criterion");
    } finally {
      setDeletingId(null);
    }
  }

  const addAction = (
    <div className="flex items-center gap-2">
      <Button asChild variant="outline">
        <Link to="/qualification/check">Quick check a company</Link>
      </Button>
      <Button asChild>
        <Link to="/qualification/criteria/new">Add criterion</Link>
      </Button>
    </div>
  );

  if (error) {
    return (
      <div>
        <PageHeader
          eyebrow="Qualification"
          title="Qualification Criteria"
          action={addAction}
        />
        <Card>
          <ErrorState message={error} onRetry={loadCriteria} />
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        <PageHeader
          eyebrow="Qualification"
          title="Qualification Criteria"
          action={addAction}
        />
        <Card className="p-6">
          <SkeletonLines lines={6} />
        </Card>
      </div>
    );
  }

  const pageCount = Math.max(1, Math.ceil(data.items.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const rows = data.items.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <div>
      <PageHeader
        eyebrow="Qualification"
        title={`Qualification Criteria (${data.total})`}
        description="What makes a company worth pursuing — defined here, judged automatically later."
        action={addAction}
      />

      <Card className="p-0">
        {data.items.length === 0 ? (
          <EmptyState
            icon={ClipboardCheck}
            title="No qualification criteria yet"
            description="Add a criterion (e.g. minimum IT spend, digital-transformation maturity) so companies can be judged against it."
            action={
              <Button asChild>
                <Link to="/qualification/criteria/new">Add a criterion</Link>
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
                  <TableHead>Disqualifying</TableHead>
                  <TableHead>Active</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((criterion) => (
                  <TableRow key={criterion.id}>
                    <TableCell className="whitespace-normal">{criterion.name}</TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">
                      {criterion.description ?? "—"}
                    </TableCell>
                    <TableCell>
                      {criterion.is_disqualifying ? (
                        <Badge variant="destructive">Hard requirement</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {criterion.is_active ? (
                        <Badge variant="secondary">Active</Badge>
                      ) : (
                        <Badge variant="outline">Inactive</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <Link
                          to={`/qualification/criteria/${criterion.id}/edit`}
                          className="text-sm text-primary-text hover:underline"
                        >
                          Edit
                        </Link>
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          disabled={deletingId === criterion.id}
                          onClick={() => handleDelete(criterion.id)}
                        >
                          {deletingId === criterion.id ? "Deleting…" : "Delete"}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <TablePagination
              total={data.items.length}
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
