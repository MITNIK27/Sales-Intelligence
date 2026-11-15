import { useEffect, useRef, useState } from "react";
import { Ban } from "lucide-react";

import type { CompanyHistory } from "@/api/types";
import { Checkbox } from "@/components/Checkbox";
import { SimpleSelect } from "@/components/SimpleSelect";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { checkDismissal, dismissCompanies } from "@/features/companies/api";
import { errorMessage } from "@/features/companies/lib/contacts";
import {
  describeHistory,
  dismissalSummary,
} from "@/features/companies/notAFit/history";
import {
  NOT_A_FIT_REASONS,
  NOTE_MAX_CHARS,
} from "@/features/companies/notAFit/reasons";

// "Not a fit" for one company or several: pick why, add an optional note, confirm. The company is
// hidden and left out of automatic work, and the reason becomes a label that later checks of the
// search are measured against, so a reason is required.
//
// If a company already has logged outreach or sent drafts, hiding it would also hide its follow-up
// reminders, so the person is told and has to tick a box first. The server enforces the same rule,
// so a stale screen cannot skip it.
export function NotAFitButton({
  companyIds,
  label = "Not a fit",
  onDone,
}: {
  companyIds: string[];
  label?: string;
  // Called after something was changed, so the page can reload.
  onDone: () => void;
}) {
  const { showToast } = useToast();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  // null while the outreach check is running; empty when there is nothing to lose.
  const [held, setHeld] = useState<CompanyHistory[] | null>(null);
  const [checkFailed, setCheckFailed] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The parent passes a new array on every render, so the form is keyed on the ids themselves;
  // otherwise a refresh in the background would wipe what the person is typing.
  const idsRef = useRef(companyIds);
  idsRef.current = companyIds;
  const idsKey = companyIds.join(",");
  const many = companyIds.length > 1;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setHeld(null);
    setCheckFailed(false);
    setAgreed(false);
    setError(null);
    checkDismissal(idsRef.current)
      .then((result) => {
        if (!cancelled) setHeld(result.with_history);
      })
      .catch(() => {
        // The server asks again if there is anything to lose, so this is not a dead end.
        if (!cancelled) {
          setHeld([]);
          setCheckFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, idsKey]);

  const needsAgreement = (held?.length ?? 0) > 0;
  const canSubmit =
    reason !== "" && !busy && held !== null && (!needsAgreement || agreed);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await dismissCompanies({
        company_ids: idsRef.current,
        reason,
        note: note.trim() || null,
        acknowledge_history: needsAgreement && agreed,
      });
      if (result.needs_confirmation.length > 0) {
        // Outreach appeared since the check, or the check failed: ask now.
        setHeld(result.needs_confirmation);
        setAgreed(false);
        setError(
          "Some of these have outreach on record. Read the warning and tick the box to continue.",
        );
        if (result.dismissed > 0) onDone();
        return;
      }
      showToast({ description: dismissalSummary(result), variant: "success" });
      setOpen(false);
      setReason("");
      setNote("");
      onDone();
    } catch (err) {
      setError(errorMessage(err, "failed to mark as not a fit"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="action">
          <Ban className="size-4" aria-hidden="true" />
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-4" align="end">
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit) void submit();
          }}
        >
          <div>
            <p className="font-semibold">
              {many
                ? `Mark ${companyIds.length} companies as not a fit`
                : "Mark this company as not a fit"}
            </p>
            <p className="text-xs text-muted-foreground">
              {many ? "They are" : "It is"} hidden from lists and left out of
              automatic work. You can undo this.
            </p>
          </div>

          <SimpleSelect
            value={reason}
            onChange={setReason}
            label="Why is it not a fit?"
            placeholder="Why is it not a fit?"
            options={NOT_A_FIT_REASONS.map((r) => ({
              value: r.value,
              label: r.label,
            }))}
          />

          <div>
            <Textarea
              value={note}
              onChange={(event) =>
                setNote(event.target.value.slice(0, NOTE_MAX_CHARS))
              }
              placeholder="Anything else? (optional)"
              aria-label="Note"
              rows={2}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              {reason === "other"
                ? "A note helps here: it is how we learn what the search got wrong. "
                : "A short note helps us learn what the search got wrong. "}
              {note.length}/{NOTE_MAX_CHARS}
            </p>
          </div>

          {held === null && (
            <p className="text-xs text-muted-foreground">
              Checking for outreach on record…
            </p>
          )}
          {held && held.length > 0 && (
            <div
              role="alert"
              className="flex flex-col gap-2 border border-border bg-chip-warning-bg px-3 py-2 text-sm text-chip-warning-fg"
            >
              <p className="font-medium">
                {held.length === 1
                  ? "This company already has outreach on record."
                  : `${held.length} of these already have outreach on record.`}
              </p>
              <ul className="list-disc pl-5">
                {held.map((entry) => (
                  <li key={entry.company_id}>
                    {entry.company_name}: {describeHistory(entry)}
                  </li>
                ))}
              </ul>
              <p>
                Marking {held.length === 1 ? "it" : "them"} not a fit hides{" "}
                {held.length === 1 ? "it" : "them"} and stops follow-up
                reminders.
              </p>
              <label className="flex items-start gap-2">
                <Checkbox
                  checked={agreed}
                  onChange={() => setAgreed((value) => !value)}
                  label="I understand, mark it not a fit anyway"
                />
                <span>I understand, mark it not a fit anyway.</span>
              </label>
            </div>
          )}
          {checkFailed && (
            <p className="text-xs text-muted-foreground">
              Could not check for outreach on record. If there is any, you will
              be asked before anything is hidden.
            </p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!canSubmit}>
              {busy ? "Saving…" : "Mark not a fit"}
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
