// The optional extras a person can add to a look-up: an area to research the company around, and
// their own criteria to check it against. None are used unless typed.

export const MAX_CRITERIA = 10;
export const MAX_CRITERION_CHARS = 200;

export type Extras = {
  focus: string;
  // Criteria typed for this look-up. They stay with the company if it is saved.
  custom: string[];
};

export const NO_EXTRAS: Extras = { focus: "", custom: [] };

function clean(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, MAX_CRITERION_CHARS);
}

// Every criterion to send, without repeats (ignoring case) and never more than
// the server accepts.
export function allCriteria(extras: Extras): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of extras.custom) {
    const text = clean(raw);
    const key = text.toLowerCase();
    if (text && !seen.has(key) && out.length < MAX_CRITERIA) {
      seen.add(key);
      out.push(text);
    }
  }
  return out;
}

// Adds a typed criterion unless it is blank, a repeat, or the limit is reached.
export function addCustom(extras: Extras, text: string): Extras {
  const cleaned = clean(text);
  if (!cleaned) return extras;
  if (allCriteria(extras).length >= MAX_CRITERIA) return extras;
  const known = allCriteria(extras).map((c) => c.toLowerCase());
  if (known.includes(cleaned.toLowerCase())) return extras;
  return { ...extras, custom: [...extras.custom, cleaned] };
}

export function removeCustom(extras: Extras, text: string): Extras {
  return { ...extras, custom: extras.custom.filter((c) => c !== text) };
}

export function hasExtras(extras: Extras): boolean {
  return extras.focus.trim() !== "" || allCriteria(extras).length > 0;
}
