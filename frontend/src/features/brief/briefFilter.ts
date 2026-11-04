// Which offerings a brief is about. The choice can come from the address, from the Market
// Discovery run the company was opened from, or from what the person picked last time, in that
// order. Kept as plain functions so the order is tested without a screen.

export type FilterSource = "you" | "run" | "saved" | null;

export type Resolved = { ids: string[]; source: FilterSource };

export function parseIds(raw: string | null): string[] {
  if (!raw) return [];
  return [
    ...new Set(
      raw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
}

export function serializeIds(ids: string[]): string {
  return ids.join(",");
}

export function resolveOfferings(input: {
  urlIds: string[];
  runIds: string[];
  savedIds: string[];
  known: Set<string> | null;
}): Resolved {
  // An offering that no longer exists (archived or deleted) is dropped rather than shown.
  const keep = (ids: string[]) =>
    input.known ? ids.filter((id) => input.known!.has(id)) : ids;
  const url = keep(input.urlIds);
  if (url.length > 0) return { ids: url, source: "you" };
  const run = keep(input.runIds);
  if (run.length > 0) return { ids: run, source: "run" };
  const saved = keep(input.savedIds);
  if (saved.length > 0) return { ids: saved, source: "saved" };
  return { ids: [], source: null };
}

export function toggleId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
}
