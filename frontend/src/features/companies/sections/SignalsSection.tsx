import { Radar } from "lucide-react";

import type { CompanyDetail, Signal } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SignalTypeBadge } from "@/components/StatusBadge";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/format";

function emptyDescription(company: CompanyDetail): string {
  if (company.enrichment_status === "never_enriched") {
    return "Not scraped yet — click Scrape above to search for news mentions and hiring signals.";
  }
  if (company.enrichment_status === "enriched" && company.last_enriched_at) {
    return `Scraped on ${formatDate(company.last_enriched_at)} — no news mentions or hiring signals found this time.`;
  }
  return "News mentions and hiring signals will appear here once found.";
}

export function SignalsSection({
  company,
  signals,
  error,
  onRetry,
}: {
  company: CompanyDetail;
  signals: Signal[] | null;
  error: string | null;
  onRetry: () => void;
}) {
  const hasSignals = signals !== null && signals.length > 0;
  return (
    <>
      <h2 className="mb-3 mt-8 text-lg font-bold">Signals</h2>
      <Card className={hasSignals ? "p-0" : undefined}>
        {error && signals === null ? (
          <ErrorState message={error} onRetry={onRetry} />
        ) : !hasSignals ? (
          <EmptyState
            icon={Radar}
            title="No buying signals found yet"
            description={emptyDescription(company)}
          />
        ) : (
          <ul className="divide-y divide-border">
            {signals.map((signal, i) => (
              <li
                key={i}
                className="flex flex-wrap items-center gap-2 px-4 py-3"
              >
                <SignalTypeBadge type={signal.signal_type} />
                <span className="min-w-0 break-words text-sm">
                  {signal.text}
                </span>
                {signal.date && (
                  <span className="text-sm text-muted-foreground">
                    — {formatDate(signal.date)}
                  </span>
                )}
                <a
                  href={signal.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-muted-foreground hover:text-primary-text hover:underline"
                >
                  (source)
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
