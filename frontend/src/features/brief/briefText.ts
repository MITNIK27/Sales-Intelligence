import type {
  CompanyOpportunity,
  ContactRelevance,
  OfferingFit,
  Recommendation,
} from "@/api/types";
import {
  BAND_LABEL,
  ROLE_LABEL,
  VERDICT_LABEL,
  evidenceLine,
  findingKindLabel,
} from "@/features/brief/opportunityLabels";

// A one-page account brief as plain text, ready to paste into an email or notes. It says only what
// is stored, keeps the sources, and states gaps instead of leaving them out.
export function briefText(input: {
  companyName: string | null;
  opportunity: CompanyOpportunity;
  fit: OfferingFit | null;
  contacts: ContactRelevance[];
  recommendation: Recommendation | null;
}): string {
  const { companyName, opportunity, fit, contacts, recommendation } = input;
  const a = opportunity.assessment;
  const lines: string[] = [];
  lines.push(
    `${companyName ?? "Company"}: ${opportunity.area_label}${a ? ` (${VERDICT_LABEL[a.verdict]})` : ""}`,
  );
  if (opportunity.industry_context)
    lines.push(`Industry: ${opportunity.industry_context}`);

  lines.push("", `What ${companyName ?? "the company"} is doing`);
  if (!a) lines.push("Not assessed yet.");
  else {
    lines.push(a.summary);
    for (const f of a.findings) {
      const src = f.evidence.url ? ` (${f.evidence.url})` : "";
      lines.push(`- ${findingKindLabel(f.kind)}: ${f.statement}${src}`);
    }
    for (const gap of a.not_found) lines.push(`- Not found: ${gap}`);
    lines.push(
      evidenceLine(a.evidence_count, a.findings.length, a.dropped_count),
    );
  }

  lines.push("", "Best offering to lead with");
  if (!fit) lines.push("No offering chosen yet.");
  else
    lines.push(
      `${fit.product_name}: ${BAND_LABEL[fit.band]}. ${fit.reasoning}`,
    );

  const people = contacts.filter((c) => c.role && c.role !== "not_relevant");
  lines.push("", "Who to start with");
  if (people.length === 0) lines.push("No relevant people matched yet.");
  for (const p of people) {
    const by = p.source === "human" ? " (set by a person)" : "";
    lines.push(
      `- ${p.full_name ?? "Unknown"}, ${p.role_title ?? "no title"}: ${ROLE_LABEL[p.role!]}${by}`,
    );
  }

  lines.push("", "What to say");
  if (!recommendation) lines.push("Not written yet.");
  else {
    lines.push(recommendation.pitch_summary, recommendation.why_this_company);
    for (const point of recommendation.talking_points) lines.push(`- ${point}`);
  }
  return lines.join("\n");
}
