// Why a person can say a company is not a fit: a short fixed list, so the reasons can be counted
// and a later check's mistakes sorted by kind. The same values live in the backend
// (NOT_A_FIT_REASONS in backend/app/modules/review/service.py); a governance check keeps the two
// lists identical, so change them together.
export const NOT_A_FIT_REASONS = [
  { value: "wrong_industry", label: "Wrong industry" },
  { value: "wrong_size", label: "Wrong size" },
  { value: "wrong_location", label: "Wrong location" },
  { value: "not_a_real_company", label: "Not a real company" },
  { value: "already_a_customer", label: "Already a customer" },
  { value: "other", label: "Something else" },
] as const;

export type NotAFitReason = (typeof NOT_A_FIT_REASONS)[number]["value"];

// The longest note the server keeps.
export const NOTE_MAX_CHARS = 500;

export function reasonLabel(value: string | null | undefined): string {
  if (!value) return "No reason given";
  return NOT_A_FIT_REASONS.find((r) => r.value === value)?.label ?? value;
}
