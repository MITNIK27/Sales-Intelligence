import { SOURCE_KIND_LABEL } from "@/features/quicklook/callStyle";
import { formatDate } from "@/lib/format";
import { safeHref } from "@/lib/safeHref";

// A quote from the evidence, with where it came from (their site, news, a job posting), its date
// when the source gives one, and a link to open it.
export function EvidenceQuote({
  quote,
  kind,
  date,
  url,
}: {
  quote: string;
  kind: string | null;
  date: string | null;
  url: string | null;
}) {
  const href = safeHref(url);
  const label = kind ? (SOURCE_KIND_LABEL[kind] ?? null) : null;
  return (
    <p className="mt-1 break-words border-l-2 border-border pl-3 text-sm">
      <span className="italic">“{quote}”</span>{" "}
      <span className="text-muted-foreground">
        {[label, date ? formatDate(date) : null].filter(Boolean).join(", ")}
      </span>
      {href && (
        <>
          {" "}
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-text hover:underline"
          >
            Source
          </a>
        </>
      )}
    </p>
  );
}
