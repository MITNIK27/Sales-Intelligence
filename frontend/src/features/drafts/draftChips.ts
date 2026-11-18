// The one-click changes offered under a draft. Each is a plain request sent to the same rewrite as
// anything the rep types, so a chip is only a shortcut for words they could have written.
export type DraftChip = { id: string; label: string; instruction: string };

export const DRAFT_CHIPS: DraftChip[] = [
  {
    id: "shorter",
    label: "Shorter",
    instruction:
      "Make it shorter. Keep the opening line and the next step, and cut the rest to the essentials.",
  },
  {
    id: "formal",
    label: "More formal",
    instruction: "Make the tone more formal and professional.",
  },
  {
    id: "friendly",
    label: "Friendlier",
    instruction:
      "Make the tone warmer and friendlier, like a message to a colleague.",
  },
  {
    id: "plain",
    label: "Plainer words",
    instruction: "Use plainer, simpler words and shorter sentences.",
  },
  {
    id: "opening",
    label: "Stronger opening",
    instruction:
      "Make the opening line more specific to this person and company, so it earns a reply.",
  },
  {
    id: "ask",
    label: "Softer ask",
    instruction: "Make the closing ask softer and lower pressure.",
  },
];

// What to call a change when it is shown back to the rep: the chip's name when the request is
// exactly a chip's, otherwise the rep's own words, shortened.
export function describeChange(instruction: string, maxChars = 48): string {
  const chip = DRAFT_CHIPS.find((c) => c.instruction === instruction);
  if (chip) return chip.label;
  const text = instruction.trim();
  return text.length <= maxChars
    ? text
    : `${text.slice(0, maxChars - 1).trimEnd()}…`;
}

// "88 to 61 words": how the length moved, so "shorter" can be seen to have worked.
export function lengthChange(before: number, after: number): string {
  const word = (n: number) => (n === 1 ? "word" : "words");
  return before === after
    ? `${after} ${word(after)}`
    : `${before} to ${after} ${word(after)}`;
}
