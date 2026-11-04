import type {
  BuyingRole,
  CompanyOpportunity,
  ContactRelevance,
  FitBand,
  OpportunityVerdict,
} from "@/api/types";
import { humanize } from "@/lib/format";

// How a verdict reads to a person. Honest about weak evidence: "weak" and "not enough" are stated
// plainly rather than softened.
export const VERDICT_LABEL: Record<OpportunityVerdict, string> = {
  supported: "Supported by evidence",
  emerging: "Emerging",
  weak: "Weak signal",
  insufficient_evidence: "Not enough evidence",
};

export const FINDING_KIND_LABEL: Record<string, string> = {
  initiative: "Initiative",
  hiring: "Hiring",
  news: "News",
  partnership: "Partnership",
  technology: "Technology",
};

export function findingKindLabel(kind: string): string {
  return FINDING_KIND_LABEL[kind] ?? humanize(kind);
}

// The overall view first, then areas somebody chose to look into, then areas only suggested.
export function groupOpportunities(items: CompanyOpportunity[]): {
  general: CompanyOpportunity | null;
  active: CompanyOpportunity[];
  suggested: CompanyOpportunity[];
} {
  const general = items.find((o) => o.area_key === "general") ?? null;
  const areas = items.filter(
    (o) => o.area_key !== "general" && o.status !== "archived",
  );
  return {
    general,
    active: areas.filter((o) => o.status === "active"),
    suggested: areas.filter((o) => o.status === "suggested"),
  };
}

// The opportunity the brief is about: the one asked for, else the first active area, the
// whole-company view, or a suggested area. The company page's Brief and People tabs both use this,
// so they always describe the same opportunity.
export function pickOpportunity(
  items: CompanyOpportunity[],
  wantedId: string | null,
): CompanyOpportunity | null {
  const { general, active, suggested } = groupOpportunities(items);
  const areas = [...(general ? [general] : []), ...active, ...suggested];
  return (
    areas.find((o) => o.id === wantedId) ??
    active[0] ??
    general ??
    suggested[0] ??
    null
  );
}

// One honest line about how much stands behind an assessment.
export function evidenceLine(
  evidenceCount: number,
  findingCount: number,
  dropped: number,
): string {
  const base = `${findingCount} finding${findingCount === 1 ? "" : "s"} checked against ${evidenceCount} piece${evidenceCount === 1 ? "" : "s"} of evidence`;
  return dropped > 0
    ? `${base}; ${dropped} claim${dropped === 1 ? "" : "s"} left out because the quote could not be verified.`
    : `${base}.`;
}

export const BAND_LABEL: Record<FitBand, string> = {
  strong: "Strong fit",
  potential: "Possible fit",
  weak: "Weak fit",
  insufficient_evidence: "Not enough evidence",
};

export const ROLE_LABEL: Record<BuyingRole, string> = {
  decision_maker: "Decides",
  influencer: "Influences",
  user: "Would use it",
  not_relevant: "Not involved",
};

export const ROLE_ORDER: BuyingRole[] = [
  "decision_maker",
  "influencer",
  "user",
  "not_relevant",
];

// People grouped by their part in the decision, in the order a rep would approach them. People not
// judged yet come last, so they are never mistaken for "not involved".
export function groupByRole(contacts: ContactRelevance[]): {
  role: BuyingRole | null;
  people: ContactRelevance[];
}[] {
  const groups = [...ROLE_ORDER, null].map((role) => ({
    role,
    people: contacts.filter((c) => c.role === role),
  }));
  return groups.filter((g) => g.people.length > 0);
}

// The offering to show people for first: the best fit that has real support behind it.
export function defaultOffering(
  fit: { product_id: string; band: FitBand }[],
): string | null {
  return (
    fit.find((f) => f.band === "strong" || f.band === "potential")
      ?.product_id ?? null
  );
}

// "No job postings" next to "No job postings found: the careers page does not link to a board"
// says the same thing twice. Keeps the longest version of each gap and drops repeats.
export function dedupeGaps(gaps: string[]): string[] {
  const norm = (g: string) =>
    g
      .trim()
      .toLowerCase()
      .replace(/[.:]+$/, "");
  const kept: string[] = [];
  for (const gap of gaps) {
    const n = norm(gap);
    if (!n) continue;
    const covered = gaps.some((other) => {
      const o = norm(other);
      return o !== n && o.includes(n);
    });
    if (!covered && !kept.some((k) => norm(k) === n)) kept.push(gap);
  }
  return kept;
}

// Offerings that clearly fit come first; the rest (weak, or not enough evidence) are kept out of
// the way so a long list of "weak fit" does not bury the answer.
export function splitFit<T extends { band: FitBand }>(
  fit: T[],
): { fits: T[]; others: T[] } {
  const fits = fit.filter((f) => f.band === "strong" || f.band === "potential");
  return { fits, others: fit.filter((f) => !fits.includes(f)) };
}
