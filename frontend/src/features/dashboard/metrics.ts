import type { DashboardRequirement } from "@/api/types";

// Pure helpers behind the dashboard's bars and labels, kept free of React so they can be tested.

// Width (0-100) of a funnel bar relative to the first stage. The first stage is always full width;
// an empty funnel gives zero rather than dividing by zero.
export function funnelWidth(count: number, top: number): number {
  if (top <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((count / top) * 100)));
}

export type RequirementShares = {
  meets: number;
  unverified: number;
  fails: number;
  total: number;
};

// Share (0-100) of each outcome of one requirement. The three always add to 100 when there is
// anything to show, so the stacked bar never has a gap or overflows from rounding.
export function requirementShares(
  req: DashboardRequirement,
): RequirementShares {
  const total = req.meets + req.couldnt_verify + req.doesnt_meet;
  if (total === 0) return { meets: 0, unverified: 0, fails: 0, total: 0 };
  const meets = Math.round((req.meets / total) * 100);
  const fails = Math.round((req.doesnt_meet / total) * 100);
  return { meets, fails, unverified: Math.max(0, 100 - meets - fails), total };
}

// Short wording for the "Next steps" rows; unknown keys fall back to the server's own label.
const ATTENTION_LABELS: Record<string, string> = {
  ready_to_contact: "Ready to contact",
  drafts_to_review: "Drafts to review",
  follow_ups_due: "Follow-ups due",
  needs_closer_look: "Need a closer look",
  searches: "Searches to check",
};

export function attentionLabel(key: string, fallback: string): string {
  return ATTENTION_LABELS[key] ?? fallback;
}

// The funnel's "% of the step before", as a tooltip string (kept out of the visible layout).
export function funnelHint(
  label: string,
  count: number,
  percent: number | null,
): string {
  return percent === null
    ? `${label}: ${count}`
    : `${label}: ${count} (${percent}% of the step before)`;
}
