import type {
  CompanyOpportunity,
  ContactRelevance,
  OfferingFit,
  Recommendation,
} from "@/api/types";
import {
  BAND_LABEL,
  dedupeGaps,
  findingKindLabel,
} from "@/features/brief/opportunityLabels";
import { TIER_LABEL, type Tiering } from "@/features/brief/tiers";

// The connection map as plain data: what the company is doing, which of our offerings it points
// to, who to talk to and what to say, joined only where the research really links them. Pure, so
// it can be tested without drawing anything; ConnectionMap.tsx draws it.

export const MAX_FINDINGS = 8;
export const MAX_OTHER_OFFERINGS = 3;
export const MAX_PEOPLE = 6;
const COLUMN_GAP = 330;
const ROW_GAP = 104;

export type GraphKind =
  "company" | "finding" | "more" | "offering" | "person" | "message" | "gap";

export type Quote = {
  quote: string;
  date: string | null;
  url: string | null;
  kind: string | null;
};

export type NodeDetail =
  | { type: "company"; name: string; industry: string | null }
  | {
      type: "finding";
      kindLabel: string;
      statement: string;
      quote: Quote;
    }
  | {
      type: "offering";
      name: string;
      bandLabel: string;
      reasoning: string;
      quotes: Quote[];
      lead: boolean;
    }
  | {
      type: "person";
      name: string;
      title: string | null;
      tierLabel: string;
      reasoning: string | null;
      startHere: boolean;
    }
  | {
      type: "message";
      pitch: string;
      why: string;
      points: string[];
    }
  | { type: "more"; what: string; items: string[] }
  | { type: "gap"; text: string };

export type GraphNode = {
  id: string;
  kind: GraphKind;
  column: number;
  x: number;
  y: number;
  title: string;
  subtitle: string | null;
  // A short word shown on the node: the kind of finding, the fit band or the part someone plays.
  tag: string | null;
  emphasis: boolean;
  dashed: boolean;
  detail: NodeDetail;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  dashed: boolean;
  label: string | null;
};

export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };

export type GraphInput = {
  companyName: string;
  industry: string | null;
  opportunity: CompanyOpportunity;
  fit: OfferingFit[];
  focus: OfferingFit | null;
  tiering: Tiering;
  recommendation: Recommendation | null;
};

const cut = (text: string, n: number) =>
  text.length > n ? `${text.slice(0, n - 1).trimEnd()}…` : text;

type Draft = Omit<GraphNode, "x" | "y">;

function quoteOf(e: OfferingFit["evidence"][number]): Quote {
  return { quote: e.quote, date: e.date, url: e.url, kind: e.kind };
}

export function buildGraph(input: GraphInput): Graph {
  const { opportunity, fit, focus, tiering, recommendation } = input;
  const columns: Draft[][] = [[], [], [], [], []];
  const edges: GraphEdge[] = [];
  const link = (
    source: string,
    target: string,
    dashed = false,
    label: string | null = null,
  ) => edges.push({ id: `${source}>${target}`, source, target, dashed, label });

  // 0. The company.
  columns[0].push({
    id: "company",
    kind: "company",
    column: 0,
    title: input.companyName,
    subtitle: opportunity.area_label,
    tag: null,
    emphasis: true,
    dashed: false,
    detail: {
      type: "company",
      name: input.companyName,
      industry: input.industry,
    },
  });

  // 1. What the company is doing: one node per finding.
  const findings = opportunity.assessment?.findings ?? [];
  const shownFindings = findings.slice(0, MAX_FINDINGS);
  shownFindings.forEach((f, i) => {
    const id = `finding-${i}`;
    columns[1].push({
      id,
      kind: "finding",
      column: 1,
      title: cut(f.statement, 90),
      subtitle: null,
      tag: findingKindLabel(f.kind),
      emphasis: false,
      dashed: false,
      detail: {
        type: "finding",
        kindLabel: findingKindLabel(f.kind),
        statement: f.statement,
        quote: {
          quote: f.evidence.quote,
          date: f.evidence.date,
          url: f.evidence.url,
          kind: f.evidence.kind,
        },
      },
    });
    link("company", id);
  });
  if (findings.length > MAX_FINDINGS) {
    const rest = findings.slice(MAX_FINDINGS);
    columns[1].push({
      id: "findings-more",
      kind: "more",
      column: 1,
      title: `+${rest.length} more finding${rest.length === 1 ? "" : "s"}`,
      subtitle: null,
      tag: null,
      emphasis: false,
      dashed: false,
      detail: {
        type: "more",
        what: "More findings",
        items: rest.map((f) => f.statement),
      },
    });
    link("company", "findings-more");
  }
  if (findings.length === 0) {
    const text =
      dedupeGaps(opportunity.assessment?.not_found ?? [])[0] ??
      "Nothing was found about this area.";
    columns[1].push(gapNode("finding-gap", 1, "No findings yet", text));
    link("company", "finding-gap", true);
  }

  // 2. Which of our offerings it points to. The lead one is large; other clear fits are small.
  const lead = focus;
  const others = fit
    .filter(
      (f) =>
        f.product_id !== lead?.product_id &&
        (f.band === "strong" || f.band === "potential"),
    )
    .slice(0, MAX_OTHER_OFFERINGS);
  const offerings = [...(lead ? [lead] : []), ...others];
  const hashToFinding = new Map<string, string[]>();
  shownFindings.forEach((f, i) => {
    const list = hashToFinding.get(f.evidence.content_hash) ?? [];
    list.push(`finding-${i}`);
    hashToFinding.set(f.evidence.content_hash, list);
  });
  for (const o of offerings) {
    const id = `offering-${o.product_id}`;
    const isLead = o.product_id === lead?.product_id;
    columns[2].push({
      id,
      kind: "offering",
      column: 2,
      title: o.product_name,
      subtitle: isLead ? "Lead offering" : null,
      tag: BAND_LABEL[o.band],
      emphasis: isLead,
      dashed: false,
      detail: {
        type: "offering",
        name: o.product_name,
        bandLabel: BAND_LABEL[o.band],
        reasoning: o.reasoning,
        quotes: o.evidence.map(quoteOf),
        lead: isLead,
      },
    });
    const backing = new Set(
      o.evidence.flatMap((e) => hashToFinding.get(e.content_hash) ?? []),
    );
    if (backing.size > 0)
      backing.forEach((fid) => link(fid, id, false, "backs"));
    else link("company", id, true, "our inference");
  }
  if (!lead) {
    columns[2].push(
      gapNode(
        "offering-gap",
        2,
        "Not judged yet",
        "Compare our offerings with this research under “Best offering to lead with”.",
      ),
    );
    link("company", "offering-gap", true);
  }

  // 3. Who to talk to, for the lead offering: people who decide, influence or use it.
  const people = tiering.tiers.flatMap((t) =>
    t.people.map((p) => ({ person: p as ContactRelevance, tier: t.tier })),
  );
  const shownPeople = people.slice(0, MAX_PEOPLE);
  const leadId = lead ? `offering-${lead.product_id}` : null;
  for (const { person, tier } of shownPeople) {
    const id = `person-${person.contact_id}`;
    const startHere = person.contact_id === tiering.approachFirst;
    columns[3].push({
      id,
      kind: "person",
      column: 3,
      title: person.full_name ?? person.role_title ?? "Unknown",
      subtitle: person.full_name ? person.role_title : null,
      tag: TIER_LABEL[tier],
      emphasis: startHere,
      dashed: false,
      detail: {
        type: "person",
        name: person.full_name ?? "Unknown",
        title: person.role_title,
        tierLabel: TIER_LABEL[tier],
        reasoning: person.reasoning,
        startHere,
      },
    });
    if (leadId) link(leadId, id);
  }
  if (people.length > MAX_PEOPLE) {
    const rest = people.slice(MAX_PEOPLE);
    columns[3].push({
      id: "people-more",
      kind: "more",
      column: 3,
      title: `+${rest.length} more ${rest.length === 1 ? "person" : "people"}`,
      subtitle: null,
      tag: null,
      emphasis: false,
      dashed: false,
      detail: {
        type: "more",
        what: "More people",
        items: rest.map(
          ({ person }) =>
            `${person.full_name ?? "Unknown"}${person.role_title ? `, ${person.role_title}` : ""}`,
        ),
      },
    });
    if (leadId) link(leadId, "people-more");
  }
  if (lead && people.length === 0) {
    columns[3].push(
      gapNode(
        "people-gap",
        3,
        tiering.others.length > 0
          ? "Nobody judged relevant yet"
          : "No people found yet",
        "No one is known who decides, influences or would use this offering.",
      ),
    );
    if (leadId) link(leadId, "people-gap", true);
  }

  // 4. What to say.
  if (recommendation) {
    columns[4].push({
      id: "message",
      kind: "message",
      column: 4,
      title: "What to say",
      subtitle: cut(recommendation.pitch_summary, 110),
      tag: null,
      emphasis: false,
      dashed: false,
      detail: {
        type: "message",
        pitch: recommendation.pitch_summary,
        why: recommendation.why_this_company,
        points: recommendation.talking_points,
      },
    });
    if (leadId) link(leadId, "message", false, "pitch");
    const start = shownPeople.find(
      ({ person }) => person.contact_id === tiering.approachFirst,
    );
    if (start)
      link(
        `person-${start.person.contact_id}`,
        "message",
        false,
        "first message",
      );
  } else if (lead) {
    columns[4].push(
      gapNode(
        "message-gap",
        4,
        "Not written yet",
        "Write what to say under “What to say”.",
      ),
    );
    if (leadId) link(leadId, "message-gap", true);
  }

  // Positions: left to right by column, each column centred on the same line.
  const nodes: GraphNode[] = columns.flatMap((column, c) =>
    column.map((draft, i) => ({
      ...draft,
      x: c * COLUMN_GAP,
      y: (i - (column.length - 1) / 2) * ROW_GAP,
    })),
  );
  return { nodes, edges };
}

function gapNode(
  id: string,
  column: number,
  title: string,
  text: string,
): Draft {
  return {
    id,
    kind: "gap",
    column,
    title,
    subtitle: cut(text, 90),
    tag: "Not found yet",
    emphasis: false,
    dashed: true,
    detail: { type: "gap", text },
  };
}

// A node and everything on its path: what leads to it and what follows from it. Hovering a node
// lights this up and dims the rest.
export function pathOf(nodeId: string, edges: GraphEdge[]): Set<string> {
  const keep = new Set<string>([nodeId]);
  const walk = (from: "source" | "target", to: "source" | "target") => {
    const queue = [nodeId];
    while (queue.length > 0) {
      const current = queue.pop() as string;
      for (const e of edges) {
        if (e[from] === current && !keep.has(e[to])) {
          keep.add(e[to]);
          queue.push(e[to]);
        }
      }
    }
  };
  walk("source", "target");
  walk("target", "source");
  return keep;
}
