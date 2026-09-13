import { useEffect, useState } from "react";

import { apiGet, apiPost } from "@/api/client";
import { OUTREACH_ACTIVITY_TYPES, OUTREACH_CHANNELS } from "@/api/types";
import type {
  Contact,
  LogOutreachActivityRequest,
  LogOutreachActivityResponse,
  OutreachActivity,
  OutreachActivityType,
  OutreachChannel,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ACTIVITY_TYPE_LABELS: Record<OutreachActivityType, string> = {
  sent: "Sent",
  response_received: "Response received",
};

function formatActivity(activity: OutreachActivity): string {
  const when = new Date(activity.occurred_at).toLocaleString();
  const what = ACTIVITY_TYPE_LABELS[activity.activity_type];
  const variant = activity.template_variant ? ` (${activity.template_variant})` : "";
  return `${when} — ${what} via ${activity.channel}${variant}`;
}

export type PrefilledDraft = {
  draftId: string;
  channel: OutreachChannel;
  templateVariant: string;
};

export function LogOutreachActivity({
  contact,
  onLogged,
  prefilledDraft,
  onDraftSent,
}: {
  contact: Contact;
  onLogged: (contact: Contact) => void;
  // Seeded from an approved Phase B draft's "Log as Sent" action, so the rep doesn't re-type
  // fields the draft already determined. Editable afterward like any other field here.
  prefilledDraft?: PrefilledDraft | null;
  onDraftSent?: () => void;
}) {
  const [channel, setChannel] = useState<OutreachChannel>(prefilledDraft?.channel ?? "email");
  const [activityType, setActivityType] = useState<OutreachActivityType>("sent");
  const [templateVariant, setTemplateVariant] = useState(prefilledDraft?.templateVariant ?? "");
  const [urgent, setUrgent] = useState(false);
  const [logging, setLogging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [history, setHistory] = useState<OutreachActivity[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (!prefilledDraft) return;
    setChannel(prefilledDraft.channel);
    setTemplateVariant(prefilledDraft.templateVariant);
    setActivityType("sent");
  }, [prefilledDraft]);

  function loadHistory() {
    return apiGet<OutreachActivity[]>(`/contacts/${contact.id}/outreach-activities`)
      .then(setHistory)
      .catch(() => {
        // Supplementary — a failure here shouldn't block logging a new activity.
      });
  }

  useEffect(() => {
    if (showHistory) loadHistory();
  }, [showHistory, contact.id]);

  async function handleLog() {
    setLogging(true);
    setError(null);
    try {
      const body: LogOutreachActivityRequest = {
        channel,
        activity_type: activityType,
        template_variant: templateVariant.trim() || null,
        urgent: activityType === "sent" ? urgent : false,
        draft_id: prefilledDraft?.draftId ?? null,
      };
      const response = await apiPost<LogOutreachActivityResponse>(
        `/contacts/${contact.id}/outreach-activities`,
        body,
      );
      onLogged(response.contact);
      setTemplateVariant("");
      if (prefilledDraft) onDraftSent?.();
      if (showHistory) await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to log activity");
    } finally {
      setLogging(false);
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2">
      {prefilledDraft && (
        <p className="text-xs text-muted-foreground">
          Logging the approved draft as sent — fields below are pre-filled from it.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={activityType} onValueChange={(v) => setActivityType(v as OutreachActivityType)}>
          <SelectTrigger className="h-9 bg-card" aria-label="Activity type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OUTREACH_ACTIVITY_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {ACTIVITY_TYPE_LABELS[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={channel} onValueChange={(v) => setChannel(v as OutreachChannel)}>
          <SelectTrigger className="h-9 bg-card" aria-label="Channel">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OUTREACH_CHANNELS.map((c) => (
              <SelectItem key={c} value={c} className="capitalize">
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="text"
          value={templateVariant}
          onChange={(e) => setTemplateVariant(e.target.value)}
          placeholder="Template variant (optional)"
          aria-label="Template variant"
          className="h-9 w-48"
        />
        {activityType === "sent" && (
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={urgent}
              onChange={(e) => setUrgent(e.target.checked)}
            />
            Urgent (allows Thu)
          </label>
        )}
        <Button type="button" onClick={handleLog} disabled={logging} size="sm" className="h-9">
          {logging ? "Logging…" : "Log Outreach"}
        </Button>
        <button
          type="button"
          onClick={() => setShowHistory((v) => !v)}
          className="text-sm text-muted-foreground hover:text-foreground hover:underline"
        >
          {showHistory ? "Hide history" : "Show history"}
        </button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {showHistory && (
        <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
          {history === null ? (
            <li>Loading…</li>
          ) : history.length === 0 ? (
            <li>No outreach logged yet.</li>
          ) : (
            history.map((activity) => <li key={activity.id}>{formatActivity(activity)}</li>)
          )}
        </ul>
      )}
    </div>
  );
}
