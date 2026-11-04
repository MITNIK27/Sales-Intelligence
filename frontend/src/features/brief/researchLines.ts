import type { ResearchEntry } from "@/api/types";
import { timeAgo } from "@/lib/format";

// What the research collectors did, as plain lines under an assessment. Says what was checked, how
// much was found, and when, so a gap reads as "looked, found nothing" and never as silence.

export function hiringTrend(
  snapshots: ResearchEntry["snapshots"],
): "up" | "down" | "flat" | null {
  const counts = (snapshots ?? [])
    .map((s) => s.matching)
    .filter((n): n is number => typeof n === "number");
  if (counts.length < 2) return null;
  const [before, now] = [counts[counts.length - 2], counts[counts.length - 1]];
  return now > before ? "up" : now < before ? "down" : "flat";
}

const TREND_TEXT = {
  up: "more than last time",
  down: "fewer than last time",
  flat: "same as last time",
};

function checked(entry: ResearchEntry, now: number): string {
  return entry.at ? ` · checked ${timeAgo(entry.at, now)}` : "";
}

function hiringLine(entry: ResearchEntry, now: number): string {
  if (entry.error) return `Job postings: could not be checked (${entry.error})`;
  if (!entry.board) {
    return "Job postings: no public job board found on the careers page, so openings could not be checked";
  }
  const trend = hiringTrend(entry.snapshots);
  const count = `${entry.found} matching of ${entry.total_open ?? "?"} open roles`;
  const trendText = trend
    ? ` (${TREND_TEXT[trend]})`
    : " (no trend yet: one count so far)";
  return `Job postings: ${count}${trendText}${checked(entry, now)}`;
}

function simpleLine(label: string, entry: ResearchEntry, now: number): string {
  if (entry.error) return `${label}: could not be checked (${entry.error})`;
  const found = entry.found === 0 ? "nothing found" : `${entry.found} found`;
  return `${label}: ${found}${checked(entry, now)}`;
}

export function researchLines(
  research: Record<string, ResearchEntry> | null | undefined,
  now: number = Date.now(),
): string[] {
  const lines: string[] = [];
  if (research?.hiring) lines.push(hiringLine(research.hiring, now));
  if (research?.news) lines.push(simpleLine("News", research.news, now));
  if (research?.web)
    lines.push(simpleLine("Announcements and pages", research.web, now));
  if (research?.people?.summary) lines.push(research.people.summary);
  return lines;
}
