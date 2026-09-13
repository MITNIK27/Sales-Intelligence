import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import type { Product, ProductCreateRequest, ProductUpdateRequest } from "@/api/types";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export function ProductFormPage() {
  const { productId } = useParams<{ productId: string }>();
  const isEdit = productId !== undefined;
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(isEdit);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadProduct() {
    if (!productId) return;
    setLoadError(null);
    setLoading(true);
    return apiGet<Product>(`/products/${productId}`)
      .then((product) => {
        setName(product.name);
        setDescription(product.description ?? "");
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "failed to load product"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (isEdit) loadProduct();
  }, [productId]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    setSaving(true);
    try {
      if (isEdit && productId) {
        const body: ProductUpdateRequest = {
          name: name.trim(),
          description: description.trim() || null,
        };
        await apiPatch(`/products/${productId}`, body);
      } else {
        const body: ProductCreateRequest = {
          name: name.trim(),
          description: description.trim() || null,
        };
        await apiPost("/products", body);
      }
      navigate("/products");
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to save product");
    } finally {
      setSaving(false);
    }
  }

  const backLink = (
    <Link
      to="/products"
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" /> Back to products
    </Link>
  );

  if (loadError) {
    return (
      <div>
        {backLink}
        <Card>
          <ErrorState message={loadError} onRetry={loadProduct} />
        </Card>
      </div>
    );
  }

  if (loading) {
    return (
      <div>
        {backLink}
        <Card className="p-6">
          <SkeletonLines lines={4} />
        </Card>
      </div>
    );
  }

  return (
    <div>
      {backLink}
      <PageHeader
        eyebrow="Products"
        title={isEdit ? "Edit product" : "Add product"}
        description="What your organization sells — used to generate sales recommendations for companies."
      />

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="product-name">Name</Label>
              <Input
                id="product-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="product-description">Description</Label>
              <Textarea
                id="product-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
              />
            </div>
            <Button type="submit" disabled={!name.trim() || saving} className="self-start">
              {saving ? "Saving…" : isEdit ? "Save changes" : "Create product"}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
