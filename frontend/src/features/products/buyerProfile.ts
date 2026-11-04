import type { BuyerProfile } from "@/api/types";

// The editor shows each list as one item per line, which is the quickest thing to type and read.
// These pure helpers convert between that text and the lists the API stores.

export type ProfileFieldKey = keyof BuyerProfile;

export const PROFILE_FIELDS: {
  key: ProfileFieldKey;
  label: string;
  hint: string;
}[] = [
  {
    key: "buyer_functions",
    label: "Who buys it",
    hint: "Business functions that decide, not job titles (titles differ between companies).",
  },
  {
    key: "influencer_functions",
    label: "Who influences the decision",
    hint: "Functions that shape or evaluate it.",
  },
  {
    key: "problems",
    label: "Problems it addresses",
    hint: "In plain words, one per line.",
  },
  {
    key: "keywords",
    label: "Words a prospect would use",
    hint: "What a company's own text says when it needs this.",
  },
  {
    key: "area_tags",
    label: "Opportunity areas",
    hint: "One to four short areas, for example cloud migration.",
  },
];

export const EMPTY_PROFILE: BuyerProfile = {
  buyer_functions: [],
  influencer_functions: [],
  problems: [],
  keywords: [],
  area_tags: [],
};

export function toLines(items: string[]): string {
  return items.join("\n");
}

export function fromLines(text: string): string[] {
  const seen = new Set<string>();
  const items: string[] = [];
  for (const line of text.split("\n")) {
    const item = line.trim();
    if (item && !seen.has(item.toLowerCase())) {
      seen.add(item.toLowerCase());
      items.push(item);
    }
  }
  return items;
}

export function profileToText(
  profile: BuyerProfile | null | undefined,
): Record<ProfileFieldKey, string> {
  const source = profile ?? EMPTY_PROFILE;
  return {
    buyer_functions: toLines(source.buyer_functions),
    influencer_functions: toLines(source.influencer_functions),
    problems: toLines(source.problems),
    keywords: toLines(source.keywords),
    area_tags: toLines(source.area_tags),
  };
}

export function textToProfile(
  text: Record<ProfileFieldKey, string>,
): BuyerProfile {
  return {
    buyer_functions: fromLines(text.buyer_functions),
    influencer_functions: fromLines(text.influencer_functions),
    problems: fromLines(text.problems),
    keywords: fromLines(text.keywords),
    area_tags: fromLines(text.area_tags),
  };
}

export function profileStatusLabel(
  status: "generated" | "edited" | null | undefined,
  stale: boolean | undefined,
): string {
  if (!status) return "Not written yet";
  if (status === "edited") return "Edited by you";
  return stale
    ? "Generated, but the description has changed since"
    : "Generated from the description. Please review it";
}
