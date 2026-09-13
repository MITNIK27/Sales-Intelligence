import { Package } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiDelete, apiGet } from "@/api/client";
import type { ProductList } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
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

export function ProductsListPage() {
  const [data, setData] = useState<ProductList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  function loadProducts() {
    setError(null);
    return apiGet<ProductList>("/products")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load products"));
  }

  useEffect(() => {
    loadProducts();
  }, []);

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await apiDelete(`/products/${id}`);
      await loadProducts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to delete product");
    } finally {
      setDeletingId(null);
    }
  }

  const addAction = (
    <Button asChild>
      <Link to="/products/new">Add product</Link>
    </Button>
  );

  if (error) {
    return (
      <div>
        <PageHeader eyebrow="Products" title="Products" action={addAction} />
        <Card>
          <ErrorState message={error} onRetry={loadProducts} />
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        <PageHeader eyebrow="Products" title="Products" action={addAction} />
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
      <PageHeader eyebrow="Products" title={`Products (${data.total})`} action={addAction} />

      <Card className="p-0">
        {data.items.length === 0 ? (
          <EmptyState
            icon={Package}
            title="No products yet"
            description="Add a product to your catalog so it can be recommended to companies."
            action={
              <Button asChild>
                <Link to="/products/new">Add a product</Link>
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
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((product) => (
                  <TableRow key={product.id}>
                    <TableCell className="whitespace-normal">{product.name}</TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">
                      {product.description ?? "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <Link
                          to={`/products/${product.id}/edit`}
                          className="text-sm text-primary-text hover:underline"
                        >
                          Edit
                        </Link>
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          disabled={deletingId === product.id}
                          onClick={() => handleDelete(product.id)}
                        >
                          {deletingId === product.id ? "Deleting…" : "Delete"}
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
