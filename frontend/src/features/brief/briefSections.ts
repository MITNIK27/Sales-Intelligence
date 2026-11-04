import type {
  CompanyOpportunity,
  ContactRelevance,
  OfferingFit,
  Recommendation,
} from "@/api/types";
import {
  BAND_LABEL,
  VERDICT_LABEL,
  dedupeGaps,
} from "@/features/brief/opportunityLabels";
import { researchLines } from "@/features/brief/researchLines";

// The Brief shows only what exists. A new area shows a single "research this" card; once research
// has run, the sections below appear, and a section with nothing to say is not drawn at all.

export type SectionId =
  "doing" | "map" | "offering" | "start" | "say" | "gaps" | "angle";

export type SectionState = {
  researched: boolean;
  judged: boolean;
  peopleKnown: number;
  recommended: boolean;
  hasGaps: boolean;
};

// In reading order. Everything needs the research first; after that each section has its own
// condition: the offering section is always there (it holds the button that works out the fit),
// people only when somebody is known, "what to say" once an offering is judged, gaps only when
// there are any.
export function visibleSections(s: SectionState): SectionId[] {
  if (!s.researched) return [];
  const sections: SectionId[] = ["doing", "map", "offering"];
  if (s.peopleKnown > 0) sections.push("start");
  if (s.judged) sections.push("say");
  if (s.hasGaps) sections.push("gaps");
  sections.push("angle");
  return sections;
}

export function sectionTitle(
  id: SectionId,
  companyName: string | null,
): string {
  switch (id) {
    case "doing":
      return `What ${companyName ?? "the company"} is doing`;
    case "map":
      return "Connection map";
    case "offering":
      return "Best offering to lead with";
    case "start":
      return "Who to start with";
    case "say":
      return "What to say";
    case "gaps":
      return "Gaps in the research";
    case "angle":
      return "Try another angle";
  }
}

export function hasGaps(opportunity: CompanyOpportunity): boolean {
  return (
    dedupeGaps(opportunity.assessment?.not_found ?? []).length > 0 ||
    researchLines(opportunity.research).length > 0
  );
}

const cut = (text: string, n: number) =>
  text.length > n ? `${text.slice(0, n - 1).trimEnd()}…` : text;

// The one line shown next to a section's title, so a closed section still says what is inside.
export function sectionSummary(
  id: SectionId,
  data: {
    opportunity: CompanyOpportunity;
    focus: OfferingFit | null;
    lead: ContactRelevance | null;
    peopleKnown: number;
    recommendation: Recommendation | null;
  },
): string {
  const a = data.opportunity.assessment;
  switch (id) {
    case "doing":
      return a
        ? `${a.findings.length} finding${a.findings.length === 1 ? "" : "s"} · ${VERDICT_LABEL[a.verdict]}`
        : "";
    case "map":
      return "How what they do leads to what we sell, who to talk to and what to say";
    case "offering":
      return data.focus
        ? `${data.focus.product_name} · ${BAND_LABEL[data.focus.band]}`
        : "Not worked out yet";
    case "start":
      return data.lead
        ? `Start with ${data.lead.full_name ?? data.lead.role_title ?? "the top contact"}`
        : `${data.peopleKnown} known, none judged relevant yet`;
    case "say":
      return data.recommendation
        ? cut(data.recommendation.pitch_summary, 110)
        : "Not written yet";
    case "gaps":
      return "What was looked for and not found";
    case "angle":
      return "Another area, another offering, or the company as a whole";
  }
}
