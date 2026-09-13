import { Target } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiDelete, apiGet } from "@/api/client";
import type { RoleCategoryList } from "@/api/types";
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

export function RoleCategoryListPage() {
  const [data, setData] = useState<RoleCategoryList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  function loadCategories() {
    setError(null);
    return apiGet<RoleCategoryList>("/role-categories")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load categories"));
  }

  useEffect(() => {
    loadCategories();
  }, []);

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await apiDelete(`/role-categories/${id}`);
      await loadCategories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to delete category");
    } finally {
      setDeletingId(null);
    }
  }

  const addAction = (
    <Button asChild>
      <Link to="/role-categories/new">Add category</Link>
    </Button>
  );

  if (error) {
    return (
      <div>
        <PageHeader eyebrow="Role Relevance" title="Role Categories" action={addAction} />
        <Card>
          <ErrorState message={error} onRetry={loadCategories} />
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        <PageHeader eyebrow="Role Relevance" title="Role Categories" action={addAction} />
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
        eyebrow="Role Relevance"
        title={`Role Categories (${data.total})`}
        description="Which functions matter for outreach — a contact's title is matched against these, not against a fixed list."
        action={addAction}
      />

      <Card className="p-0">
        {data.items.length === 0 ? (
          <EmptyState
            icon={Target}
            title="No role categories yet"
            description="Add a category (e.g. Vendor / IT Procurement) so contacts can be classified against it."
            action={
              <Button asChild>
                <Link to="/role-categories/new">Add a category</Link>
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
                  <TableHead>Priority</TableHead>
                  <TableHead>Framing</TableHead>
                  <TableHead>Active</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((category) => (
                  <TableRow key={category.id}>
                    <TableCell className="whitespace-normal">{category.name}</TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">
                      {category.description ?? "—"}
                    </TableCell>
                    <TableCell>
                      {category.is_primary_target ? (
                        <Badge>Primary target</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="capitalize text-muted-foreground">
                      {category.framing_style}
                    </TableCell>
                    <TableCell>
                      {category.is_active ? (
                        <Badge variant="secondary">Active</Badge>
                      ) : (
                        <Badge variant="outline">Inactive</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <Link
                          to={`/role-categories/${category.id}/edit`}
                          className="text-sm text-primary-text hover:underline"
                        >
                          Edit
                        </Link>
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          disabled={deletingId === category.id}
                          onClick={() => handleDelete(category.id)}
                        >
                          {deletingId === category.id ? "Deleting…" : "Delete"}
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
