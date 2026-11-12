import { useState } from "react";

import { Button } from "@/components/ui/button";
import { reasonLabel } from "@/features/companies/notAFit/reasons";
import { formatDate } from "@/lib/format";

// Shown on a company that was marked not a fit: why, when, and a way back. The company is hidden
// from lists and left out of automatic work until it is restored.
export function DismissedBanner({
  reason,
  note,
  dismissedAt,
  onRestore,
}: {
  reason: string | null | undefined;
  note: string | null | undefined;
  dismissedAt: string;
  onRestore: () => Promise<void>;
}) {
  const [restoring, setRestoring] = useState(false);

  async function restore() {
    setRestoring(true);
    await onRestore();
    setRestoring(false);
  }

  return (
    <div
      role="status"
      className="mb-6 flex flex-wrap items-start justify-between gap-3 border border-border bg-chip-warning-bg px-4 py-3 text-chip-warning-fg"
    >
      <div className="text-sm">
        <p className="font-semibold">
          Marked not a fit: {reasonLabel(reason)}
          <span className="font-normal"> · {formatDate(dismissedAt)}</span>
        </p>
        {note && <p className="mt-1">{note}</p>}
        <p className="mt-1">
          It is hidden from lists and left out of automatic work, and no draft
          can be written for it, until you restore it.
        </p>
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={restore}
        disabled={restoring}
      >
        {restoring ? "Restoring…" : "Undo"}
      </Button>
    </div>
  );
}
