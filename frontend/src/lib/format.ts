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

// The spellings dates arrive in: ISO, "3/9/2026" and "Sep 25, 2026". Anything else is left alone,
// because the browser will guess a date out of loose text (it reads "Fall 2026" as 1 Jan 2026).
const DATE_SHAPES = [
  /^\d{4}-\d{2}-\d{2}/,
  /^\d{1,2}\/\d{1,2}\/\d{2,4}$/,
  /^[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}$/,
];

const validDate = (iso: string): Date | null => {
  if (!DATE_SHAPES.some((shape) => shape.test(iso.trim()))) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};

export function shortDate(iso: string): string {
  const d = validDate(iso);
  return d
    ? d.toLocaleDateString(undefined, { day: "numeric", month: "short" })
    : iso;
}

// A calendar date with no time, e.g. "5 Oct 2026". Text that is not a date is shown unchanged, so a
// scraped value such as "Fall 2026" never turns into "Invalid Date".
export function formatDate(iso: string): string {
  const d = validDate(iso);
  return d
    ? d.toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : iso;
}

// A date with the time, e.g. "5 Oct 2026, 14:54".
export function formatDateTime(iso: string): string {
  const d = validDate(iso);
  return d
    ? d.toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : iso;
}

// A readable version of a stored key we have no label for: "needs_review" becomes "Needs review".
export function humanize(key: string): string {
  const spaced = key.replace(/[_-]+/g, " ").trim();
  return spaced ? spaced[0].toUpperCase() + spaced.slice(1) : key;
}

const JOB_STATUS: Record<string, string> = {
  pending: "Waiting to start",
  running: "In progress",
  done: "Finished",
  failed: "Did not finish",
};

export function jobStatusLabel(status: string): string {
  return JOB_STATUS[status] ?? humanize(status);
}

// How many words a text has: runs of non-space characters, so "Hi, Sam." is two.
export function countWords(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}
