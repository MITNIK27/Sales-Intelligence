import type { BuyingRole, ContactRelevance } from "@/api/types";

// The buying hierarchy of people at a company: who decides, who influences, who would use it.
// The tier comes from the person's stored role (the model's, or the person's own override); within
// a tier people are ordered by how senior their title reads, so the first name is where to start.

export type Tier = "decides" | "influences" | "uses";

export const TIER_ORDER: Tier[] = ["decides", "influences", "uses"];

export const TIER_LABEL: Record<Tier, string> = {
  decides: "Decides",
  influences: "Influences",
  uses: "Evaluates and uses",
};

export const TIER_HINT: Record<Tier, string> = {
  decides: "Sponsor or budget owner: has the final say.",
  influences: "Champion or department head: shapes the decision.",
  uses: "Evaluator or end user: judges whether it works.",
};

const TIER_OF: Partial<Record<BuyingRole, Tier>> = {
  decision_maker: "decides",
  influencer: "influences",
  user: "uses",
};

// Lower is more senior. Matched as whole words in the title and the stored seniority.
const RANKS: [number, string[]][] = [
  [
    0,
    [
      "chief",
      "ceo",
      "cto",
      "cio",
      "coo",
      "cfo",
      "cmo",
      "president",
      "founder",
      "owner",
    ],
  ],
  [
    1,
    [
      "svp",
      "evp",
      "vp",
      "vice president",
      "managing director",
      "general manager",
    ],
  ],
  [2, ["head", "director"]],
  [3, ["manager", "lead", "principal", "architect"]],
];

function words(text: string): string {
  return ` ${text.toLowerCase().replace(/[^a-z0-9]+/g, " ")} `;
}

export function seniorityRank(person: {
  role_title: string | null;
  seniority: string | null;
}): number {
  const text = words(`${person.role_title ?? ""} ${person.seniority ?? ""}`);
  for (const [rank, terms] of RANKS) {
    if (terms.some((t) => text.includes(` ${t} `))) return rank;
  }
  return 4;
}

export type TieredPerson = ContactRelevance & { rank: number };

export type Tiering = {
  tiers: { tier: Tier; people: TieredPerson[] }[];
  // Not involved, or not judged yet: kept out of the tiers so they are never mistaken for a lead.
  others: ContactRelevance[];
  // The best person to approach first: the most senior in the highest tier that decides or
  // influences. Null when nobody does.
  approachFirst: string | null;
};

export function tierPeople(contacts: ContactRelevance[]): Tiering {
  const tiers = TIER_ORDER.map((tier) => ({
    tier,
    people: contacts
      .filter((c) => c.role && TIER_OF[c.role] === tier)
      .map((c) => ({ ...c, rank: seniorityRank(c) }))
      .sort((a, b) => a.rank - b.rank),
  }));
  const others = contacts.filter((c) => !c.role || !TIER_OF[c.role]);
  // Only people who decide or influence are worth approaching first; an end user is not a lead.
  const top = tiers
    .filter((t) => t.tier !== "uses")
    .find((t) => t.people.length > 0)?.people[0];
  return {
    tiers: tiers.filter((t) => t.people.length > 0),
    others,
    approachFirst: top?.contact_id ?? null,
  };
}
