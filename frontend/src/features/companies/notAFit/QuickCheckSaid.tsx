import type { QuickCheckNote } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import type { Call } from "@/features/quicklook/api";
import { CALL_TITLE } from "@/features/quicklook/callStyle";
import { formatDate } from "@/lib/format";

// What Quick Check said about this website, kept on the company so the reason it looked like a
// fit, or not, is still in front of the person after it becomes a company.
export function QuickCheckSaid({ note }: { note: QuickCheckNote | null | undefined }) {
  if (!note) return null;
  const title = CALL_TITLE[note.call as Call] ?? note.call;
  return (
    <Card className="mb-6">
      <CardContent className="text-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          What Quick Check said · {formatDate(note.updated_at)}
        </p>
        <p className="mt-1 font-semibold">{title}</p>
        {note.call_reason && <p className="mt-1">{note.call_reason}</p>}
        {note.relevance && (
          <p className="mt-1 text-muted-foreground">{note.relevance}</p>
        )}
      </CardContent>
    </Card>
  );
}
