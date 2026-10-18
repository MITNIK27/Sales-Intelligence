// One place for how numbers and times read across the app, so "19 h ago" and "1,250" never
// appear in two different spellings.

const numberFormat = new Intl.NumberFormat(undefined);

export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return count === 1 ? one : many;
}

// "just now", "5 min ago", "19 h ago", "3 days ago". `now` is injectable so it can be tested.
export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(
    0,
    Math.round((now - new Date(iso).getTime()) / 1000),
  );
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} ${plural(days, "day")} ago`;
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

// A calendar date with no time, e.g. "5 Oct 2026".
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
