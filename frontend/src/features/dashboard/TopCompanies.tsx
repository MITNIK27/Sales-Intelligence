import { Link } from "react-router-dom";
import { WebsiteLink } from "@/components/WebsiteLink";

import type { DashboardTopCompany } from "@/api/types";
import { SkeletonLines } from "@/components/Skeleton";

const SHOWN = 3;

// The strongest opportunities by Priority Score. The one-line reason is on hover; the full
// reasoning is one click away on the company page.
export function TopCompanies({
  companies,
}: {
  companies: DashboardTopCompany[] | null;
}) {
  if (companies === null) return <SkeletonLines lines={3} />;
  if (companies.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No scored companies yet. The best opportunities appear here after a
        search.
      </p>
    );
  }
  return (
    <ol className="flex flex-col divide-y divide-border">
      {companies.slice(0, SHOWN).map((company, index) => (
        <li
          key={company.company_id}
          title={company.reason ?? undefined}
          className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
        >
          <span className="w-5 text-sm font-semibold tabular-nums text-muted-foreground">
            {index + 1}
          </span>
          <div className="min-w-0 flex-1">
            <Link
              to={`/companies/${company.company_id}`}
              className="block truncate text-sm font-medium hover:underline focus-visible:outline-2 focus-visible:outline-primary"
            >
              {company.name}
            </Link>
            {company.domain && (
              <div>
                <WebsiteLink
                  domain={company.domain}
                  className="max-w-full text-xs"
                />
              </div>
            )}
          </div>
          <span
            className="shrink-0 bg-primary/10 px-2 py-0.5 text-sm font-semibold tabular-nums"
            title="Priority Score out of 100: fit, size, industry, signals, news, technology and contacts"
          >
            {company.score != null ? Math.round(company.score) : "—"}
          </span>
        </li>
      ))}
    </ol>
  );
}
