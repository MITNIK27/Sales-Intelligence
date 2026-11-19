import { useState } from "react";

import { apiPatch, apiPost } from "@/api/client";
import type {
  Contact,
  ContactTrackingUpdate,
  OutreachActivity,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { ContactTracking } from "@/features/contacts/ContactTracking";
import {
  countSent,
  followUpHeadline,
  hasReplied,
  sequenceStatus,
} from "@/features/outreach/outreachRules";

const SNOOZES = [
  { label: "1 day", days: 1 },
  { label: "2 days", days: 2 },
  { label: "1 week", days: 5 },
];

// The follow-up tab: where this person is in the sequence and when the next message is due, with the
// three things a rep does about it: write the follow-up, push it back, or stop. The manual form is
// still here, folded away, for anything these do not cover.
export function FollowUpPanel({
  contact,
  history,
  onContactUpdated,
  onWriteFollowUp,
}: {
  contact: Contact;
  history: OutreachActivity[] | null;
  onContactUpdated: (contact: Contact) => void;
  // Switch to the draft tab, which starts on the next message in the sequence.
  onWriteFollowUp: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const touches = countSent(history);
  const replied = hasReplied(history);
  const status = sequenceStatus(touches);
  const due = contact.next_follow_up_at;

  async function run(action: () => Promise<Contact>) {
    setBusy(true);
    setError(null);
    try {
      onContactUpdated(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not save that");
    } finally {
      setBusy(false);
    }
  }

  const snooze = (days: number) =>
    run(() =>
      apiPost<Contact>(`/contacts/${contact.id}/follow-up/snooze`, {
        business_days: days,
      }),
    );

  const stop = () =>
    run(() => {
      const update: ContactTrackingUpdate = {
        status:
          contact.status === "follow_up_scheduled"
            ? "contacted"
            : contact.status,
        next_follow_up_at: null,
        next_follow_up_channel: null,
        timezone: contact.timezone,
      };
      return apiPatch<Contact>(`/contacts/${contact.id}/tracking`, update);
    });

  const canAct = !(replied && !due);

  return (
    <div className="mt-3 flex flex-col gap-3">
      {history === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <p className="text-sm font-semibold">
          {followUpHeadline({ touchesSent: touches, dueAt: due, replied })}
        </p>
      )}

      {history !== null && canAct && (
        <div className="flex flex-wrap items-center gap-3">
          {!status.complete && (
            <Button type="button" size="sm" onClick={onWriteFollowUp}>
              {touches === 0 ? "Write the first message" : "Write follow-up"}
            </Button>
          )}
          <span className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
            Remind me in
            {SNOOZES.map((s) => (
              <Button
                key={s.days}
                type="button"
                size="sm"
                variant="action"
                disabled={busy}
                onClick={() => void snooze(s.days)}
              >
                {s.label}
              </Button>
            ))}
          </span>
          {due && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => void stop()}
            >
              Stop follow-ups
            </Button>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <details className="text-sm text-muted-foreground">
        <summary className="cursor-pointer">Edit the details by hand</summary>
        <ContactTracking
          key={`${contact.status}|${contact.next_follow_up_at}|${contact.next_follow_up_channel}|${contact.timezone}`}
          contact={contact}
          onSaved={onContactUpdated}
        />
      </details>
    </div>
  );
}
