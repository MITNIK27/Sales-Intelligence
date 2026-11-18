import { ArrowUp, Loader2, Sparkles, Undo2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { Draft } from "@/api/types";
import { Button } from "@/components/ui/button";
import { refineDraft, undoDraft } from "@/features/drafts/api";
import {
  DRAFT_CHIPS,
  describeChange,
  lengthChange,
} from "@/features/drafts/draftChips";
import { countWords } from "@/lib/format";

const MAX_REQUEST_CHARS = 600;

// "Describe your message": under a generated draft, the rep says what to change and the draft is
// rewritten in place, so there is no need to take it to another tool. It rewrites the text as it is
// on screen (hand edits included), keeps the email's structure, and never sends anything. Undo goes
// back one version. The three places drafts are edited all use this, so they behave the same.
export function DraftAssistant({
  draftId,
  subject,
  body,
  initialRevisions = 0,
  disabled = false,
  disabledReason,
  onRewritten,
}: {
  draftId: string;
  subject: string;
  body: string;
  initialRevisions?: number;
  disabled?: boolean;
  disabledReason?: string;
  // The rewritten (or restored) draft; the caller puts its text into its editor.
  onRewritten: (draft: Draft) => void;
}) {
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState<"rewrite" | "undo" | null>(null);
  const [revisions, setRevisions] = useState(initialRevisions);
  const [error, setError] = useState<string | null>(null);
  const [change, setChange] = useState<string | null>(null);

  async function rewrite(instruction: string) {
    const text = instruction.trim();
    if (!text || busy || disabled) return;
    const before = countWords(body);
    setBusy("rewrite");
    setError(null);
    try {
      const draft = await refineDraft(draftId, text, subject || null, body);
      onRewritten(draft);
      setRevisions(draft.revision_count ?? revisions + 1);
      setChange(
        `${describeChange(text)}: ${lengthChange(before, countWords(draft.body))}`,
      );
      setRequest("");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "could not rewrite the draft",
      );
    } finally {
      setBusy(null);
    }
  }

  async function undo() {
    if (busy || disabled) return;
    setBusy("undo");
    setError(null);
    try {
      const draft = await undoDraft(draftId);
      onRewritten(draft);
      setRevisions(draft.revision_count ?? Math.max(0, revisions - 1));
      setChange("Went back to the earlier version");
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not undo");
    } finally {
      setBusy(null);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void rewrite(request);
  }

  const working = busy !== null;
  return (
    <div className="flex flex-col gap-2" aria-busy={working}>
      <form
        onSubmit={submit}
        className="flex items-center gap-2 rounded-full border border-border bg-muted px-4 py-1.5 focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/30"
      >
        <Sparkles className="size-4 shrink-0 text-primary" aria-hidden="true" />
        <input
          type="text"
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          maxLength={MAX_REQUEST_CHARS}
          disabled={disabled || working}
          placeholder={
            working && busy === "rewrite"
              ? "Rewriting…"
              : "Describe your message, e.g. keep it under 60 words and mention their cloud move"
          }
          aria-label="Describe how to change this draft"
          className="min-w-0 flex-1 bg-transparent py-1.5 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
        />
        <Button
          type="submit"
          size="icon"
          aria-label="Rewrite the draft"
          disabled={disabled || working || request.trim().length < 2}
          className="size-8 rounded-full"
        >
          {busy === "rewrite" ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : (
            <ArrowUp aria-hidden="true" />
          )}
        </Button>
      </form>

      <div className="flex flex-wrap items-center gap-2">
        {DRAFT_CHIPS.map((chip) => (
          <button
            key={chip.id}
            type="button"
            disabled={disabled || working}
            onClick={() => void rewrite(chip.instruction)}
            className="border border-border bg-card px-3 py-1 text-sm hover:border-ring hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
          >
            {chip.label}
          </button>
        ))}
        {revisions > 0 && (
          <button
            type="button"
            disabled={disabled || working}
            onClick={() => void undo()}
            className="ml-auto inline-flex items-center gap-1 px-2 py-1 text-sm font-medium text-primary-text hover:underline focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Undo2 className="size-4" aria-hidden="true" />
            Undo
          </button>
        )}
      </div>

      {disabled && disabledReason && (
        <p className="text-xs text-muted-foreground">{disabledReason}</p>
      )}
      {change && !error && (
        <p role="status" className="text-xs text-muted-foreground">
          {change}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
