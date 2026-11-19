import { useState } from "react";

import { Button } from "@/components/ui/button";
import { composeText, gmailComposeUrl } from "@/features/outreach/compose";

// TEMPORARY. A stopgap until the app is connected to the rep's own Gmail (sign-in first, then a
// mailbox connection that can send from here and read sent mail and replies back). Until then the
// rep sends from their own Gmail, and this asks them to confirm so the log stays right. When the
// connection exists, this whole component and `compose.ts` are replaced by a "Send" button in the
// same place, and nothing else in the app needs to change: confirming writes the same log entry the
// connection will write itself.
export function SendFromMail({
  to,
  subject,
  body,
  busy,
  error,
  onConfirmSent,
  onChangeDetails,
}: {
  // The person's email address, or null when none is on file.
  to: string | null;
  subject: string;
  body: string;
  busy: boolean;
  error: string | null;
  // The rep says they sent it: save and log it.
  onConfirmSent: () => void;
  // Let the rep set the date or add a note before logging.
  onChangeDetails: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const [copied, setCopied] = useState(false);

  const url = to ? gmailComposeUrl({ to, subject, body }) : null;
  const why = !to
    ? "There is no email address on file for this person."
    : url === null
      ? "This message is too long to open in Gmail. Use Copy instead."
      : null;

  async function copy() {
    try {
      await window.navigator.clipboard.writeText(composeText(subject, body));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // The browser refused: the text is still on screen to select.
    }
  }

  function openGmail() {
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
    setAsking(true);
  }

  return (
    <div className="flex flex-col gap-2" aria-label="Send this message">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void copy()}
        >
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={!url}
          title={why ?? "Opens a new message in your Gmail"}
          onClick={openGmail}
        >
          Open in Gmail
        </Button>
        {!asking && (
          <button
            type="button"
            onClick={() => setAsking(true)}
            className="text-sm text-primary-text hover:underline"
          >
            I sent it another way
          </button>
        )}
      </div>
      {why && <p className="text-xs text-muted-foreground">{why}</p>}

      {asking && (
        <div
          role="group"
          aria-label="Confirm it was sent"
          className="flex flex-wrap items-center gap-3 border border-primary bg-card px-3 py-2"
        >
          <span className="text-sm font-semibold">Did you send it?</span>
          <Button
            type="button"
            size="sm"
            disabled={busy}
            onClick={onConfirmSent}
          >
            {busy ? "Logging…" : "Yes, log it"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="action"
            disabled={busy}
            onClick={() => setAsking(false)}
          >
            Not yet
          </Button>
          <button
            type="button"
            onClick={onChangeDetails}
            className="text-sm text-primary-text hover:underline"
          >
            Change the date or add a note
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
