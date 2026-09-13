import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import type {
  QualificationCriterion,
  QualificationCriterionCreateRequest,
  QualificationCriterionUpdateRequest,
} from "@/api/types";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export function CriterionFormPage() {
  const { criterionId } = useParams<{ criterionId: string }>();
  const isEdit = criterionId !== undefined;
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isDisqualifying, setIsDisqualifying] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [loading, setLoading] = useState(isEdit);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadCriterion() {
    if (!criterionId) return;
    setLoadError(null);
    setLoading(true);
    return apiGet<QualificationCriterion>(`/qualification/criteria/${criterionId}`)
      .then((criterion) => {
        setName(criterion.name);
        setDescription(criterion.description ?? "");
        setIsDisqualifying(criterion.is_disqualifying);
        setIsActive(criterion.is_active);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "failed to load criterion"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (isEdit) loadCriterion();
  }, [criterionId]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    setSaving(true);
    try {
      if (isEdit && criterionId) {
        const body: QualificationCriterionUpdateRequest = {
          name: name.trim(),
          description: description.trim() || null,
          is_disqualifying: isDisqualifying,
          is_active: isActive,
        };
        await apiPatch(`/qualification/criteria/${criterionId}`, body);
      } else {
        const body: QualificationCriterionCreateRequest = {
          name: name.trim(),
          description: description.trim() || null,
          is_disqualifying: isDisqualifying,
          is_active: isActive,
        };
        await apiPost("/qualification/criteria", body);
      }
      navigate("/qualification/criteria");
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to save criterion");
    } finally {
      setSaving(false);
    }
  }

  const backLink = (
    <Link
      to="/qualification/criteria"
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" /> Back to qualification criteria
    </Link>
  );

  if (loadError) {
    return (
      <div>
        {backLink}
        <Card>
          <ErrorState message={loadError} onRetry={loadCriterion} />
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
        eyebrow="Qualification"
        title={isEdit ? "Edit criterion" : "Add criterion"}
        description="What a company needs to show to be worth pursuing — reasoned against later, not hardcoded."
      />

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="criterion-name">Name</Label>
              <Input
                id="criterion-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Minimum IT spend"
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="criterion-description">Description</Label>
              <Textarea
                id="criterion-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What the evidence needs to show for this to be considered met — this is what gets reasoned against."
                rows={4}
              />
            </div>
            <div className="flex flex-col gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={isDisqualifying}
                  onChange={(e) => setIsDisqualifying(e.target.checked)}
                />
                Hard requirement — failing this criterion alone disqualifies the company
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                />
                Active — used when judging companies
              </label>
            </div>
            <Button type="submit" disabled={!name.trim() || saving} className="self-start">
              {saving ? "Saving…" : isEdit ? "Save changes" : "Create criterion"}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
