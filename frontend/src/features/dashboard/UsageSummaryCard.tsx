import { useEffect, useState } from "react";

import { apiGet } from "@/api/client";
import type { UsageSummary } from "@/api/types";
import { byProvider, formatCost } from "@/features/dashboard/usage";
import { formatNumber } from "@/lib/format";

// What the AI models, web search and context.dev were asked to do in the last 30 days, with an
// estimated cost. The cost is from published prices and is shown even on free tiers (so the
// budget is visible before it is needed); it is not a bill. A failed load just hides the card.
export function UsageSummaryCard() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  useEffect(() => {
    apiGet<UsageSummary>("/usage/summary?days=30")
      .then(setUsage)
      .catch(() => undefined);
  }, []);

  if (!usage || usage.lines.length === 0) return null;
  return (
    <div
      className="border-t border-border pt-4 text-sm"
      title="Estimated from published prices, shown at paid-equivalent even on free tiers. Not a bill."
    >
      <div className="flex items-baseline justify-between">
        <span>Estimated cost, last {usage.days} days</span>
        <span className="font-semibold tabular-nums">
          {formatCost(usage.total_est_cost_usd)}
        </span>
      </div>
      <ul className="mt-2 flex flex-col gap-1 text-muted-foreground">
        {byProvider(usage.lines).map((p) => (
          <li key={p.provider} className="flex justify-between">
            <span>
              {p.provider}: {formatNumber(p.calls)} calls
              {p.errors > 0 ? `, ${p.errors} failed` : ""}
            </span>
            <span className="tabular-nums">{formatCost(p.cost)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
