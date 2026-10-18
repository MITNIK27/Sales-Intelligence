import { AlertTriangle, CheckCircle2 } from "lucide-react";

import type { DashboardHealth } from "@/api/types";
import { SkeletonLines } from "@/components/Skeleton";
import { MetricBar } from "@/features/dashboard/parts";
import { formatNumber, plural } from "@/lib/format";

const BRANCH_LABELS: Record<string, string> = {
  signals: "news lookups",
  contact_search: "contact searches",
  company_data: "company data",
  page_contacts: "website contacts",
};

// What the work cost and whether anything went wrong, in two short lines. Only context.dev credits
// are tracked today; the usage of the AI model and web search is not recorded anywhere yet, which
// is said on hover rather than in the layout.
export function CostHealth({ health }: { health: DashboardHealth | null }) {
  if (health === null) return <SkeletonLines lines={3} />;
  const ceiling = health.credit_ceiling;
  const errors = Object.entries(health.provider_errors);
  const allGood =
    !health.budget_exhausted &&
    health.enrichment_failed === 0 &&
    errors.length === 0;
  return (
    <div className="flex flex-col gap-4 text-sm">
      <div title="context.dev credits. Usage of the AI model and web search is not tracked yet, so it is not shown.">
        <div className="flex items-baseline justify-between">
          <span>context.dev credits</span>
          <span className="tabular-nums">
            <span className="font-semibold">
              {formatNumber(health.credits_used)}
            </span>
            {ceiling ? (
              <span className="text-muted-foreground">
                {" "}
                / {formatNumber(ceiling)} per search
              </span>
            ) : null}
          </span>
        </div>
        {ceiling ? (
          <div className="mt-1.5">
            <MetricBar
              segments={[
                { value: health.credits_used, className: "bg-primary" },
              ]}
              total={ceiling}
              label={`${health.credits_used} of ${ceiling} credits used`}
            />
          </div>
        ) : null}
      </div>

      {allGood ? (
        <p
          className="flex items-center gap-2 text-muted-foreground"
          title={`${health.companies_needing_no_paid_lookup} ${plural(
            health.companies_needing_no_paid_lookup,
            "company",
            "companies",
          )} needed no paid lookup`}
        >
          <CheckCircle2 className="size-4 text-success" aria-hidden="true" /> No
          problems reported
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {health.budget_exhausted && (
            <li className="flex items-start gap-2">
              <AlertTriangle
                className="mt-0.5 size-4 text-warning"
                aria-hidden="true"
              />
              Credit limit reached — later companies used scraper data only.
            </li>
          )}
          {health.enrichment_failed > 0 && (
            <li className="flex items-start gap-2">
              <AlertTriangle
                className="mt-0.5 size-4 text-warning"
                aria-hidden="true"
              />
              {health.enrichment_failed}{" "}
              {plural(health.enrichment_failed, "company", "companies")} could
              not be enriched.
            </li>
          )}
          {errors.map(([branch, n]) => (
            <li key={branch} className="flex items-start gap-2">
              <AlertTriangle
                className="mt-0.5 size-4 text-warning"
                aria-hidden="true"
              />
              {n} {BRANCH_LABELS[branch] ?? branch} failed (companies kept).
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
