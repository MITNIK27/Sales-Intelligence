import { useState } from "react";

import type { CompanyDetail, Product } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { NeedsReviewBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { NotAFitButton } from "@/features/companies/notAFit/NotAFitButton";

// The title, and (for a company still flagged for review) the Confirm action. Confirming resumes
// the automated pipeline. Which offerings to pitch is chosen on the Brief tab, so nothing is asked
// here: a Market Discovery run pitches its own offerings, a single offering is used as it is, and
// otherwise the best match is found.
export function CompanyHeader({
  company,
  products,
  fromRun,
  onConfirm,
  onDismissed,
}: {
  company: CompanyDetail;
  products: Product[] | null;
  // The offerings are the ones chosen for the Market Discovery run.
  fromRun: boolean;
  onConfirm: (productIds: string[]) => Promise<void>;
  // After the company was marked not a fit, so the page can reload.
  onDismissed: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  async function confirm() {
    const fixed =
      products && (products.length === 1 || (fromRun && products.length > 0));
    setConfirming(true);
    try {
      await onConfirm(fixed ? products.map((p) => p.id) : []);
    } finally {
      setConfirming(false);
    }
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
                <Button
                  type="button"
                  className="text-sm font-semibold"
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
