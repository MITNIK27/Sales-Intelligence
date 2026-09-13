import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import { FRAMING_STYLES } from "@/api/types";
import type {
  FramingStyle,
  RoleCategory,
  RoleCategoryCreateRequest,
  RoleCategoryUpdateRequest,
} from "@/api/types";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const FRAMING_STYLE_LABELS: Record<FramingStyle, string> = {
  business: "Business — outcome/cost-savings language",
  technical: "Technical — technical/KPI language",
};

export function RoleCategoryFormPage() {
  const { roleCategoryId } = useParams<{ roleCategoryId: string }>();
  const isEdit = roleCategoryId !== undefined;
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isPrimaryTarget, setIsPrimaryTarget] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [framingStyle, setFramingStyle] = useState<FramingStyle>("business");
  const [loading, setLoading] = useState(isEdit);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadCategory() {
    if (!roleCategoryId) return;
    setLoadError(null);
    setLoading(true);
    return apiGet<RoleCategory>(`/role-categories/${roleCategoryId}`)
      .then((category) => {
        setName(category.name);
        setDescription(category.description ?? "");
        setIsPrimaryTarget(category.is_primary_target);
        setIsActive(category.is_active);
        setFramingStyle(category.framing_style);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "failed to load category"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (isEdit) loadCategory();
  }, [roleCategoryId]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    setSaving(true);
    try {
      if (isEdit && roleCategoryId) {
        const body: RoleCategoryUpdateRequest = {
          name: name.trim(),
          description: description.trim() || null,
          is_primary_target: isPrimaryTarget,
          is_active: isActive,
          framing_style: framingStyle,
        };
        await apiPatch(`/role-categories/${roleCategoryId}`, body);
      } else {
        const body: RoleCategoryCreateRequest = {
          name: name.trim(),
          description: description.trim() || null,
          is_primary_target: isPrimaryTarget,
          is_active: isActive,
          framing_style: framingStyle,
        };
        await apiPost("/role-categories", body);
      }
      navigate("/role-categories");
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to save category");
    } finally {
      setSaving(false);
    }
  }

  const backLink = (
    <Link
      to="/role-categories"
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" /> Back to role categories
    </Link>
  );

  if (loadError) {
    return (
      <div>
        {backLink}
        <Card>
          <ErrorState message={loadError} onRetry={loadCategory} />
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
        eyebrow="Role Relevance"
        title={isEdit ? "Edit role category" : "Add role category"}
        description="What function this represents — a contact's title is matched against this by inferred meaning, not by keyword."
      />

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="category-name">Name</Label>
              <Input
                id="category-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Vendor / IT Procurement"
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="category-description">Description</Label>
              <Textarea
                id="category-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What this function typically does, example titles — this is what grounds the match."
                rows={4}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="category-framing">Draft framing</Label>
              <Select
                value={framingStyle}
                onValueChange={(v) => setFramingStyle(v as FramingStyle)}
              >
                <SelectTrigger id="category-framing" className="h-9 bg-card">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FRAMING_STYLES.map((style) => (
                    <SelectItem key={style} value={style}>
                      {FRAMING_STYLE_LABELS[style]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Which register Phase B drafts use for contacts matched to this category.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={isPrimaryTarget}
                  onChange={(e) => setIsPrimaryTarget(e.target.checked)}
                />
                Primary target — surfaced first when prioritizing outreach
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                />
                Active — used when classifying contacts
              </label>
            </div>
            <Button type="submit" disabled={!name.trim() || saving} className="self-start">
              {saving ? "Saving…" : isEdit ? "Save changes" : "Create category"}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
