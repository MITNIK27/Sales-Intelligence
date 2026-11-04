import type { UsageLine } from "@/api/types";

export type ProviderUsage = {
  provider: string;
  calls: number;
  errors: number;
  cost: number;
};

// Per-provider totals, most expensive first, so the biggest spender is the first line.
export function byProvider(lines: UsageLine[]): ProviderUsage[] {
  const totals = new Map<string, ProviderUsage>();
  for (const line of lines) {
    const t = totals.get(line.provider) ?? {
      provider: line.provider,
      calls: 0,
      errors: 0,
      cost: 0,
    };
    t.calls += line.calls;
    t.errors += line.errors;
    t.cost += line.est_cost_usd;
    totals.set(line.provider, t);
  }
  return [...totals.values()].sort(
    (a, b) => b.cost - a.cost || b.calls - a.calls,
  );
}

// Small amounts keep their precision ("$0.0042"); larger ones read as money ("$12.40").
export function formatCost(usd: number): string {
  if (usd === 0) return "$0";
  return usd < 1 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}
