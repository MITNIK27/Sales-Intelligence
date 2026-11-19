import type { Contact, OutreachActivity, OutreachOutcome } from "@/api/types";

// The words and rules for logging outreach and following up, kept apart from the screens so they
// can be checked. The server decides what a log does to the follow-up; the lines here only say it.

// A first message and up to three follow-ups, then stop.
export const MAX_FOLLOW_UPS = 3;

export const OUTCOME_LABELS: Record<OutreachOutcome, string> = {
  interested: "Interested",
  not_now: "Not now",
  not_interested: "Not interested",
  referred: "Referred me on",
  out_of_office: "Out of office",
};

// What logging each reply does, said before it is saved.
export const OUTCOME_HINTS: Record<OutreachOutcome, string> = {
  interested: "Follow-ups stop.",
  referred: "Follow-ups stop.",
  not_interested: "Follow-ups stop. They stay on file.",
  not_now: "You will be reminded later.",
  out_of_office: "You will be reminded after they are back.",
};

// How long to wait before reminding, in business days, for a reply that asks to wait.
export const WAIT_CHOICES = [
  { label: "In a week", days: 5 },
  { label: "In two weeks", days: 10 },
  { label: "In a month", days: 20 },
] as const;

export const OUTCOME_WAITS: OutreachOutcome[] = ["not_now", "out_of_office"];

export type WhenChoice = "today" | "yesterday" | "date";

const DAY_MS = 24 * 60 * 60 * 1000;
const MAX_AGE_DAYS = 365;

// The time to send for "when did it happen". `iso: null` means now (the server stamps it).
export function whenToIso(
  choice: WhenChoice,
  dateValue: string,
  now: Date = new Date(),
): { iso: string | null } | { error: string } {
  if (choice === "today") return { iso: null };
  if (choice === "yesterday")
    return { iso: new Date(now.getTime() - DAY_MS).toISOString() };
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateValue);
  if (!match) return { error: "Pick a date." };
  const [, y, m, d] = match;
  const picked = new Date(Number(y), Number(m) - 1, Number(d), 12, 0, 0);
  if (Number.isNaN(picked.getTime())) return { error: "Pick a date." };
  const sameDay =
    picked.getFullYear() === now.getFullYear() &&
    picked.getMonth() === now.getMonth() &&
    picked.getDate() === now.getDate();
  if (sameDay) return { iso: null };
  if (picked.getTime() > now.getTime())
    return { error: "That date is in the future." };
  if (now.getTime() - picked.getTime() > MAX_AGE_DAYS * DAY_MS)
    return { error: "That date is more than a year ago." };
  return { iso: picked.toISOString() };
}

export function countSent(history: OutreachActivity[] | null): number {
  return (history ?? []).filter((a) => a.activity_type === "sent").length;
}

export function hasReplied(history: OutreachActivity[] | null): boolean {
  return (history ?? []).some((a) => a.activity_type === "response_received");
}

export type SequenceStatus = {
  label: string;
  complete: boolean;
  // Which follow-up is next (1 to 3), or null when there is none to write.
  nextFollowUp: number | null;
};

// Where a person is in the sequence, from how many messages were logged as sent to them: the first
// message counts as one, so after it the next one is follow-up 1.
export function sequenceStatus(touchesSent: number): SequenceStatus {
  if (touchesSent <= 0)
    return {
      label: "No message sent yet",
      complete: false,
      nextFollowUp: null,
    };
  if (touchesSent <= MAX_FOLLOW_UPS)
    return {
      label: `Follow-up ${touchesSent} of ${MAX_FOLLOW_UPS}`,
      complete: false,
      nextFollowUp: touchesSent,
    };
  return {
    label: `All ${MAX_FOLLOW_UPS} follow-ups sent`,
    complete: true,
    nextFollowUp: null,
  };
}

// "Mon 24 Nov".
export function dueLabel(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, {
        weekday: "short",
        day: "numeric",
        month: "short",
      });
}

function timeLabel(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

// The headline on the follow-up tab: where they are in the sequence and when the next one is due.
export function followUpHeadline({
  touchesSent,
  dueAt,
  replied,
}: {
  touchesSent: number;
  dueAt: string | null;
  replied: boolean;
}): string {
  if (replied && !dueAt) return "They replied. No follow-up is scheduled.";
  const status = sequenceStatus(touchesSent);
  if (status.complete)
    return dueAt
      ? `${status.label}, no reply yet. Reminder on ${dueLabel(dueAt)}.`
      : `${status.label}, no reply yet.`;
  if (touchesSent <= 0) return "No message sent yet, so nothing to follow up.";
  return dueAt
    ? `${status.label}, due ${dueLabel(dueAt)}`
    : `${status.label}, not scheduled`;
}

// One line after a log, saying what happens next.
export function afterLogLine(
  contact: Pick<Contact, "next_follow_up_at">,
): string {
  if (contact.next_follow_up_at)
    return `Logged. Next follow-up: ${dueLabel(contact.next_follow_up_at)} at ${timeLabel(contact.next_follow_up_at)}.`;
  return "Logged. Follow-ups stopped.";
}
