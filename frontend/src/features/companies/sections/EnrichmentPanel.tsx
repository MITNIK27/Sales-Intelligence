import type { CompanyDetail, JobStatus } from "@/api/types";
import { EnrichmentStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";

export function EnrichmentPanel({
  company,
  scrapeJob,
  triggering,
  onScrape,
}: {
  company: CompanyDetail;
  scrapeJob: JobStatus | null;
  triggering: boolean;
  onScrape: () => void;
}) {
  const inFlight = company.enrichment_status === "pending" || triggering;
  return (
    <Card className="mt-6">
      <CardContent>
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <EnrichmentStatusBadge status={company.enrichment_status} />
            {company.last_enriched_at && (
              <span className="text-sm text-muted-foreground">
                last enriched {formatDateTime(company.last_enriched_at)}
              </span>
            )}
          </div>
          <Button type="button" onClick={onScrape} disabled={inFlight}>
            {inFlight
              ? "Scraping…"
              : company.enrichment_status === "never_enriched"
                ? "Scrape"
                : "Re-scrape"}
          </Button>
        </div>
        {company.enrichment_status === "failed" && company.enrichment_error && (
          <p className="mt-3 text-sm text-destructive">
            {company.enrichment_error}
          </p>
        )}
        {scrapeJob?.status === "running" && scrapeJob.progress && (
          <p className="mt-3 text-sm text-muted-foreground">
            Step {scrapeJob.progress.done} of {scrapeJob.progress.total}…
          </p>
        )}
      </CardContent>
    </Card>
  );
}
