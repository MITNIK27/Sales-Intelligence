import { Lightbulb } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Product, Recommendation } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { OfferingPicker } from "@/components/OfferingPicker";
import { SkeletonLines } from "@/components/Skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCompanyFits } from "@/features/companies/hooks/useSuggestedOfferings";
import {
  EVERY_BAND,
  suggestedOfferings,
} from "@/features/companies/lib/suggestedOfferings";
import { formatDateTime } from "@/lib/format";

function RecommendationCard({
  recommendation,
  product,
}: {
  recommendation: Recommendation;
  product: Product | undefined;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-bold">
          {product?.name ?? "Recommendation"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm">{recommendation.pitch_summary}</p>
        <p className="mt-3 text-sm text-muted-foreground">
          {recommendation.why_this_company}
        </p>
        {recommendation.talking_points.length > 0 && (
          <ul className="mt-3 list-inside list-disc text-sm">
            {recommendation.talking_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          {recommendation.model_used} ·{" "}
          {formatDateTime(recommendation.created_at)}
        </p>
      </CardContent>
    </Card>
  );
}

export function RecommendationsSection({
  companyId,
  recommendations,
  error,
  products,
  onGenerate,
  onRetry,
}: {
  companyId: string;
  recommendations: Recommendation[] | null;
  error: string | null;
  products: Product[] | null;
  onGenerate: (productId: string) => Promise<void>;
  onRetry: () => void;
}) {
  // One offering at a time: a rep picks exactly one to research right now.
  const [productId, setProductId] = useState("");
  const [generating, setGenerating] = useState(false);
  const researched = suggestedOfferings(
    useCompanyFits(companyId),
    products ?? [],
    Infinity,
    EVERY_BAND,
  );

  async function generate() {
    setGenerating(true);
    await onGenerate(productId);
    setGenerating(false);
  }

  return (
    <>
      <h2 className="mb-3 mt-8 text-lg font-bold">Recommendations</h2>
      <Card>
        <CardContent>
          <div className="flex flex-wrap items-center gap-3">
            <OfferingPicker
              products={products ?? []}
              researched={researched}
              value={productId}
              onChange={setProductId}
            />
            <Button
              type="button"
              onClick={generate}
              disabled={!productId || generating}
            >
              {generating ? "Generating…" : "Generate Recommendation"}
            </Button>
          </div>
          {products && products.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              No offerings added yet —{" "}
              <Link
                to="/products/new"
                className="text-primary-text hover:underline"
              >
                add one
              </Link>{" "}
              before generating a recommendation.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="mt-4">
        {error ? (
          <Card>
            <ErrorState message={error} onRetry={onRetry} />
          </Card>
        ) : !recommendations ? (
          <Card className="p-6">
            <SkeletonLines lines={4} />
          </Card>
        ) : recommendations.length === 0 ? (
          <Card>
            <EmptyState
              icon={Lightbulb}
              title="No recommendations yet"
              description="Pick an offering above and generate one to see sales-prep talking points for this company."
            />
          </Card>
        ) : (
          <div className="flex flex-col gap-4">
            {recommendations.map((recommendation) => (
              <RecommendationCard
                key={recommendation.id}
                recommendation={recommendation}
                product={(products ?? []).find(
                  (p) => p.id === recommendation.product_id,
                )}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
