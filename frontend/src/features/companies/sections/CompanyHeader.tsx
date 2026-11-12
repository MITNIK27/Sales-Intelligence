import { useEffect, useState } from "react";

import type { CompanyDetail, Product } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { ProductMultiSelect } from "@/components/ProductMultiSelect";
import { NeedsReviewBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { NotAFitButton } from "@/features/companies/notAFit/NotAFitButton";

// The title, and (for a company still flagged for review) the offerings to pitch and the Confirm
// action. Confirming resumes the automated pipeline, which may pitch more than one offering.
export function CompanyHeader({
  company,
  products,
  fromRun,
  onConfirm,
  onDismissed,
}: {
  company: CompanyDetail;
  products: Product[] | null;
  // The offerings are the ones chosen for the Market Discovery run, so they start selected.
  fromRun: boolean;
  onConfirm: (productIds: string[]) => Promise<void>;
  // After the company was marked not a fit, so the page can reload.
  onDismissed: () => void;
}) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);

  // Exactly one offering, or the run's own offerings, means there is nothing to choose between.
  useEffect(() => {
    if (products && (products.length === 1 || (fromRun && products.length > 0)))
      setSelectedIds(products.map((p) => p.id));
  }, [products, fromRun]);

  async function confirm() {
    setConfirming(true);
    await onConfirm(selectedIds);
    setConfirming(false);
  }

  return (
    <PageHeader
      title={
        <span className="inline-flex items-center gap-2">
          {company.name}
          {company.needs_review && (
            <NeedsReviewBadge reason={company.needs_review_reason} />
          )}
        </span>
      }
      action={
        // A company marked not a fit has its own banner with an Undo; nothing else applies to it.
        company.dismissed_at ? undefined : (
          <div className="flex items-end gap-2">
            {company.needs_review && (
          <div className="flex flex-col items-end gap-2">
            {fromRun && products && products.length > 0 && (
              <p className="text-sm text-muted-foreground">
                Pitching: {products.map((p) => p.name).join(", ")}
              </p>
            )}
            {!fromRun && products && products.length > 1 && (
              <ProductMultiSelect
                products={products}
                selectedIds={new Set(selectedIds)}
                onToggle={(productId) =>
                  setSelectedIds((current) =>
                    current.includes(productId)
                      ? current.filter((id) => id !== productId)
                      : [...current, productId],
                  )
                }
              />
            )}
            <Button
              type="button"
              size="sm"
              onClick={confirm}
              disabled={confirming}
            >
              {confirming ? "Confirming…" : "Confirm Company"}
            </Button>
          </div>
            )}
            <NotAFitButton companyIds={[company.id]} onDone={onDismissed} />
          </div>
        )
      }
    />
  );
}
