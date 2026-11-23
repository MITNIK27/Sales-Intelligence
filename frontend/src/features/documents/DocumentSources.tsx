import { FileText } from "lucide-react";
import { Link } from "react-router-dom";

import type { KnowledgeRef } from "@/api/types";

// Which of our documents a model used when it wrote about an offering. Only passages its text cites
// are listed; each opens the document in the library.
export function DocumentSources({
  refs,
}: {
  refs: KnowledgeRef[] | null | undefined;
}) {
  const cited = (refs ?? []).filter((r) => r.cited);
  if (cited.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="font-semibold text-muted-foreground">
        From our documents:
      </span>
      {cited.map((ref) => (
        <Link
          key={ref.label}
          to={`/documents?document=${encodeURIComponent(ref.document_id)}`}
          className="inline-flex items-center gap-1 border border-border px-2 py-0.5 hover:border-primary hover:text-primary-text"
        >
          <FileText className="size-3" aria-hidden="true" />
          <span className="font-semibold">{ref.label}</span>
          {ref.document_name} · {ref.locator}
        </Link>
      ))}
    </div>
  );
}
