import type { Tone } from "@/components/StatusTag";
import type {
  Call,
  CriterionVerdict,
  OfferingBand,
} from "@/features/quicklook/api";

// The top-line answer, in words a salesperson would say. The word always carries the meaning; the
// tone only colours it.
export const CALL_TITLE: Record<Call, string> = {
  yes: "Worth pitching: Yes",
  maybe: "Worth pitching: Maybe",
  no: "No clear opening yet",
  unclear: "Not enough information to say",
};

export const CALL_TONE: Record<Call, Tone> = {
  yes: "good",
  maybe: "watch",
  no: "bad",
  unclear: "neutral",
};

// Where a piece of evidence came from, in plain words.
export const SOURCE_KIND_LABEL: Record<string, string> = {
  site: "Their website",
  news: "News",
  hiring: "Job posting",
  search: "Web search",
};

// Same words as the Brief uses for how well an offering fits.
export const OFFERING_BAND_LABEL: Record<OfferingBand, string> = {
  strong: "Strong fit",
  potential: "Possible fit",
  weak: "Weak fit",
};

export const OFFERING_BAND_TONE: Record<OfferingBand, Tone> = {
  strong: "good",
  potential: "watch",
  weak: "neutral",
};

// How a criterion the person asked about came out. Unknown is the honest default when the evidence
// found does not say.
export const CRITERION_LABEL: Record<CriterionVerdict, string> = {
  met: "Met",
  not_met: "Not met",
  unknown: "Unknown",
};

export const CRITERION_TONE: Record<CriterionVerdict, Tone> = {
  met: "good",
  not_met: "bad",
  unknown: "neutral",
};

// The steps shown while a look-up runs. They are indicative: the server answers in one go.
export const LOOKUP_STEPS = [
  "Finding the company",
  "Reading their website",
  "Matching to our offerings",
] as const;

// Which step to show as current after this many seconds of waiting.
export function lookupStep(seconds: number): number {
  if (seconds < 3) return 0;
  if (seconds < 9) return 1;
  return 2;
}
