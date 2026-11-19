import { Check, ExternalLink, Reply, Send } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { apiPost } from "@/api/client";
import { CHANNEL_LABELS, OUTREACH_OUTCOMES } from "@/api/types";
import type {
  Contact,
  Draft,
  LogOutreachActivityRequest,
  LogOutreachActivityResponse,
  OutreachActivity,
  OutreachChannel,
  OutreachOutcome,
} from "@/api/types";
import { SimpleSelect } from "@/components/SimpleSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { DRAFT_TYPE_LABELS } from "@/features/drafts/draftTypes";
import { linkedinUrlOf } from "@/features/outreach/compose";
import {
  OUTCOME_HINTS,
  OUTCOME_LABELS,
  OUTCOME_WAITS,
  WAIT_CHOICES,
  afterLogLine,
  whenToIso,
  type WhenChoice,
} from "@/features/outreach/outreachRules";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Mode = "sent" | "reply";
type Source = "draft" | "own";

const HISTORY_SHOWN = 5;

const MODES: { id: Mode; label: string; hint: string; icon: typeof Send }[] = [
  {
    id: "sent",
    label: "I sent a message",
    hint: "Log a message that went out",
    icon: Send,
  },
  {
    id: "reply",
    label: "They replied",
    hint: "Log what they said back",
    icon: Reply,
  },
];

const WHEN_OPTIONS: { id: WhenChoice; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "date", label: "Pick a date" },
];

// One labelled row of the form: the label on the left, the control on the right (stacked on a
// phone), so every row lines up.
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-[8rem_1fr] sm:items-center sm:gap-4">
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {children}
      </div>
    </div>
  );
}

// A small set of choices as chips. Lighter than the filled buttons, so a form of several of them
// does not turn into a wall of red; the chosen one carries a check, so it does not rely on colour.
function Chips<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { id: T; label: string }[];
  value: T | null;
  onChange: (id: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = o.id === value;
        return (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.id)}
            className={cn(
              "inline-flex h-9 items-center gap-1.5 border px-3 text-sm transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
              on
                ? "border-primary bg-primary/10 font-medium text-foreground"
                : "border-border bg-card text-foreground hover:border-primary/60 hover:bg-muted",
            )}
          >
            {on && (
              <Check className="size-3.5 text-primary" aria-hidden="true" />
            )}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function describe(activity: OutreachActivity): string {
  const via = CHANNEL_LABELS[activity.channel];
  if (activity.activity_type === "sent") return `Sent by ${via}`;
  return activity.outcome
    ? `Replied by ${via}: ${OUTCOME_LABELS[activity.outcome]}`
    : `Replied by ${via}`;
}

// Log what happened, the way a rep thinks of it: "I sent a message" or "they replied". It says when
// (today unless told otherwise), which draft it was, and what the reply said, and the server turns
// that into the next follow-up. The draft the rep is working on is offered first.
export function LogOutreachActivity({
  contact,
  draft,
  history,
  onLogged,
  onHistoryChanged,
  onDraftLogged,
}: {
  contact: Contact;
  // The draft currently being worked on for this person, if any.
  draft: Draft | null;
  history: OutreachActivity[] | null;
  onLogged: (contact: Contact) => void;
  onHistoryChanged: () => void;
  // The draft was logged as sent from here, so the draft panel must stop showing it.
  onDraftLogged: () => void;
}) {
  const [mode, setMode] = useState<Mode>("sent");
  const [source, setSource] = useState<Source>(draft ? "draft" : "own");
  const [channel, setChannel] = useState<OutreachChannel>("email");
  const [when, setWhen] = useState<WhenChoice>("today");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [urgent, setUrgent] = useState(false);
  const [outcome, setOutcome] = useState<OutreachOutcome | null>(null);
  const [waitDays, setWaitDays] = useState<number>(20);
  const [logging, setLogging] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  // A draft appearing (or going away) changes what "which message" offers.
  const draftId = draft?.id ?? null;
  useEffect(() => {
    setSource(draftId ? "draft" : "own");
  }, [draftId]);

  const fromDraft = mode === "sent" && source === "draft" && draft !== null;
  const effectiveChannel: OutreachChannel = fromDraft ? "email" : channel;
  const waits = mode === "reply" && outcome && OUTCOME_WAITS.includes(outcome);
  const profile = linkedinUrlOf(contact);
  const name = contact.full_name ?? "this person";

  function pickOutcome(next: OutreachOutcome) {
    setOutcome(next);
    setWaitDays(next === "out_of_office" ? 5 : 20);
    setError(null);
  }

  async function handleLog() {
    setError(null);
    setResult(null);
    const when_ = whenToIso(when, date);
    if ("error" in when_) {
      setError(when_.error);
      return;
    }
    if (mode === "reply" && !outcome) {
      setError("Pick what they said.");
      return;
    }
    setLogging(true);
    try {
      const body: LogOutreachActivityRequest = {
        channel: effectiveChannel,
        activity_type: mode === "sent" ? "sent" : "response_received",
        notes: note.trim() || null,
        occurred_at: when_.iso,
        urgent: mode === "sent" ? urgent : false,
        draft_id: fromDraft ? draft!.id : null,
        outcome: mode === "reply" ? outcome : null,
        follow_up_in_business_days: waits ? waitDays : null,
      };
      const response = await apiPost<LogOutreachActivityResponse>(
        `/contacts/${contact.id}/outreach-activities`,
        body,
      );
      onLogged(response.contact);
      setResult(afterLogLine(response.contact));
      setNote("");
      setOutcome(null);
      setWhen("today");
      setDate("");
      setUrgent(false);
      if (fromDraft) onDraftLogged();
      onHistoryChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not log that");
    } finally {
      setLogging(false);
    }
  }

  const shown = showAll
    ? (history ?? [])
    : (history ?? []).slice(0, HISTORY_SHOWN);

  return (
    <div className="mt-3 flex flex-col gap-5">
      <div className="overflow-hidden border border-border bg-card">
        <div
          role="radiogroup"
          aria-label="What happened"
          className="grid grid-cols-2 border-b border-border"
        >
          {MODES.map((m) => {
            const on = m.id === mode;
            const Icon = m.icon;
            return (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => {
                  setMode(m.id);
                  setError(null);
                  setResult(null);
                }}
                className={cn(
                  "flex items-start gap-3 border-b-2 px-4 py-3 text-left transition-colors",
                  "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
                  on
                    ? "border-primary bg-primary/5"
                    : "border-transparent hover:bg-muted",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 flex size-8 shrink-0 items-center justify-center",
                    on
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  <Icon className="size-4" aria-hidden="true" />
                </span>
                <span className="min-w-0">
                  <span
                    className={cn(
                      "block text-sm font-semibold",
                      !on && "text-muted-foreground",
                    )}
                  >
                    {m.label}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {m.hint}
                  </span>
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex flex-col gap-4 px-4 py-4">
          {mode === "sent" && draft && (
            <Field label="Message">
              <SimpleSelect
                label="Which message"
                value={source}
                onChange={(v) => setSource(v as Source)}
                options={[
                  {
                    value: "draft",
                    label: `${DRAFT_TYPE_LABELS[draft.draft_type]} draft${
                      draft.subject ? `: ${draft.subject}` : ""
                    }`,
                  },
                  { value: "own", label: "Something I wrote myself" },
                ]}
                className="w-full max-w-md"
              />
            </Field>
          )}

          <Field label="Channel">
            {fromDraft ? (
              <span className="text-sm">
                {CHANNEL_LABELS.email}
                <span className="text-muted-foreground">
                  {" "}
                  (drafts are emails)
                </span>
              </span>
            ) : (
              <Chips<OutreachChannel>
                label="Channel"
                value={channel}
                onChange={setChannel}
                options={[
                  { id: "email", label: CHANNEL_LABELS.email },
                  { id: "linkedin", label: CHANNEL_LABELS.linkedin },
                ]}
              />
            )}
            {effectiveChannel === "linkedin" && profile && (
              <a
                href={profile}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sm font-medium text-primary-text hover:underline"
              >
                Open LinkedIn profile
                <ExternalLink className="size-3.5" aria-hidden="true" />
              </a>
            )}
          </Field>

          <Field label="When">
            <Chips<WhenChoice>
              label="When it happened"
              value={when}
              onChange={setWhen}
              options={WHEN_OPTIONS}
            />
            {when === "date" && (
              <Input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                aria-label="Date"
                className="h-9 w-auto"
              />
            )}
          </Field>

          {mode === "reply" && (
            <Field label="What they said">
              <div className="flex flex-col gap-2">
                <Chips<OutreachOutcome>
                  label="What they said"
                  value={outcome}
                  onChange={pickOutcome}
                  options={OUTREACH_OUTCOMES.map((o) => ({
                    id: o,
                    label: OUTCOME_LABELS[o],
                  }))}
                />
                {outcome && (
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-xs text-muted-foreground">
                      {OUTCOME_HINTS[outcome]}
                    </span>
                    {waits && (
                      <SimpleSelect
                        label="Remind me"
                        value={String(waitDays)}
                        onChange={(v) => setWaitDays(Number(v))}
                        options={WAIT_CHOICES.map((c) => ({
                          value: String(c.days),
                          label: `Remind me ${c.label.toLowerCase()}`,
                        }))}
                        className="w-48"
                      />
                    )}
                  </div>
                )}
              </div>
            </Field>
          )}

          <Field label="Note">
            <Textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              rows={2}
              placeholder={
                mode === "sent"
                  ? "Optional, e.g. mentioned their new plant in Ohio"
                  : "Optional, e.g. asked for pricing for 20 seats"
              }
              aria-label="Note"
              className="max-w-xl"
            />
          </Field>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-muted/40 px-4 py-3">
          <div className="min-w-0 text-sm">
            {error ? (
              <span role="alert" className="text-destructive">
                {error}
              </span>
            ) : result ? (
              <span role="status" className="text-success">
                {result}
              </span>
            ) : mode === "sent" ? (
              <label className="flex items-center gap-2 text-muted-foreground">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={urgent}
                  onChange={(e) => setUrgent(e.target.checked)}
                />
                Allow a Thursday follow-up
              </label>
            ) : (
              <span className="text-muted-foreground">
                The follow-up is updated from what they said.
              </span>
            )}
          </div>
          <Button
            type="button"
            disabled={logging}
            onClick={() => void handleLog()}
          >
            {logging
              ? "Logging…"
              : mode === "sent"
                ? "Log as sent"
                : "Log reply"}
          </Button>
        </div>
      </div>

      {history !== null && (
        <section aria-label="What has been logged">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            History{history.length > 0 ? ` (${history.length})` : ""}
          </h3>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing logged for {name} yet.
            </p>
          ) : (
            <ol className="flex flex-col">
              {shown.map((a, i) => {
                const Icon = a.activity_type === "sent" ? Send : Reply;
                const last = i === shown.length - 1;
                return (
                  <li key={a.id} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className="flex size-7 shrink-0 items-center justify-center bg-muted text-muted-foreground">
                        <Icon className="size-3.5" aria-hidden="true" />
                      </span>
                      {!last && <span className="w-px flex-1 bg-border" />}
                    </div>
                    <div className={cn("min-w-0 flex-1", !last && "pb-3")}>
                      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                        <span className="text-sm font-medium">
                          {describe(a)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatDateTime(a.occurred_at)}
                        </span>
                      </div>
                      {a.notes && (
                        <p className="text-sm text-muted-foreground">
                          {a.notes}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          {history.length > HISTORY_SHOWN && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="mt-1 text-sm text-primary-text hover:underline"
            >
              {showAll ? "Show fewer" : `Show all ${history.length}`}
            </button>
          )}
        </section>
      )}
    </div>
  );
}
