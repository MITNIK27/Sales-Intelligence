import { useState } from "react";

import { apiPatch } from "@/api/client";
import { FOLLOW_UP_CHANNELS, TRACKING_STATUSES } from "@/api/types";
import type { Contact, ContactTrackingUpdate, FollowUpChannel, TrackingStatus } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

function toDateInputValue(iso: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 10); // yyyy-mm-dd, good enough for a <input type="date">
}

export function ContactTracking({ contact }: { contact: Contact }) {
  const [status, setStatus] = useState<TrackingStatus>(contact.status);
  const [followUpDate, setFollowUpDate] = useState(toDateInputValue(contact.next_follow_up_at));
  const [channel, setChannel] = useState<FollowUpChannel | "">(
    contact.next_follow_up_channel ?? "",
  );
  const [timezone, setTimezone] = useState(contact.timezone ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const update: ContactTrackingUpdate = {
        status,
        next_follow_up_at: followUpDate ? new Date(followUpDate).toISOString() : null,
        next_follow_up_channel: channel || null,
        timezone: timezone.trim() || null,
      };
      await apiPatch(`/contacts/${contact.id}/tracking`, update);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <Select value={status} onValueChange={(v) => setStatus(v as TrackingStatus)}>
        <SelectTrigger className="h-9 bg-card" aria-label="Tracking status">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {TRACKING_STATUSES.map((s) => (
            <SelectItem key={s} value={s} className="capitalize">
              {s.replace(/_/g, " ")}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        type="date"
        value={followUpDate}
        onChange={(e) => setFollowUpDate(e.target.value)}
        aria-label="Next follow-up date"
        className="h-9 w-auto"
      />
      <Select
        value={channel || "none"}
        onValueChange={(v) => setChannel(v === "none" ? "" : (v as FollowUpChannel))}
      >
        <SelectTrigger className="h-9 bg-card" aria-label="Follow-up channel">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">— channel —</SelectItem>
          {FOLLOW_UP_CHANNELS.map((c) => (
            <SelectItem key={c} value={c} className="capitalize">
              {c}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        type="text"
        value={timezone}
        onChange={(e) => setTimezone(e.target.value)}
        placeholder="Timezone, e.g. Europe/Berlin (optional)"
        aria-label="Timezone"
        className="h-9 w-56"
      />
      <Button type="button" onClick={handleSave} disabled={saving} size="sm" className="h-9">
        {saving ? "Saving…" : "Save"}
      </Button>
      {saved && <span className="text-sm text-success">Saved</span>}
      {error && <span className="text-sm text-destructive">{error}</span>}
    </div>
  );
}
