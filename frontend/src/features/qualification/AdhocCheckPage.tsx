import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPost } from "@/api/client";
import type {
  AdhocQualificationCheckRequest,
  JobStatus,
  QualificationResult,
  ScrapeJobStarted,
} from "@/api/types";
import { QualificationResultsTable } from "@/features/qualification/QualificationResultsTable";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const POLL_INTERVAL_MS = 1500;

type AdhocQualifyJobResult = {
  company_id: string;
  company_name: string;
  company_domain: string | null;
  company_created: boolean;
};

export function AdhocCheckPage() {
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [qualificationResults, setQualificationResults] = useState<QualificationResult[] | null>(
    null,
  );
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  const canSubmit = name.trim() !== "" || domain.trim() !== "";
  const jobResult = (job?.result as unknown as AdhocQualifyJobResult | null) ?? null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setStarting(true);
    setJob(null);
    setQualificationResults(null);
    try {
      const body: AdhocQualificationCheckRequest = {
        name: name.trim() || null,
        domain: domain.trim() || null,
      };
      const started = await apiPost<ScrapeJobStarted>("/qualification/check", body);
      pollRef.current = window.setInterval(async () => {
        const status = await apiGet<JobStatus>(`/jobs/${started.job_id}`);
        setJob(status);
        if (status.status === "done" || status.status === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          if (status.status === "done" && status.result) {
            const companyId = (status.result as unknown as AdhocQualifyJobResult).company_id;
            const results = await apiGet<QualificationResult[]>(
              `/companies/${companyId}/qualification-results`,
            );
            setQualificationResults(results);
          }
        }
      }, POLL_INTERVAL_MS);
      setName("");
      setDomain("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to start qualification check");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Qualification"
        title="Quick Check"
        description="Enrich and judge a company against your active criteria right now — takes a few seconds, no upload or discovery run needed."
      />

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="check-name">Company name</Label>
              <Input
                id="check-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Acme Inc — not a URL, use Domain for that"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="check-domain">Domain</Label>
              <Input
                id="check-domain"
                type="text"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="e.g. acme.com"
              />
            </div>
            <p className="text-xs text-muted-foreground">Provide at least a name or a domain.</p>
            <Button type="submit" disabled={!canSubmit || starting} className="self-start">
              {starting ? "Starting…" : "Check company"}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </form>
        </CardContent>
      </Card>

      {job && (
        <div className="mt-6">
          {(job.status === "pending" || job.status === "running") && (
            <p className="text-sm text-muted-foreground">Enriching and judging…</p>
          )}
          {job.status === "failed" && <p className="text-sm text-destructive">{job.error}</p>}
          {job.status === "done" && jobResult && (
            <>
              <div className="mb-3 flex items-center gap-3">
                <Link
                  to={`/companies/${jobResult.company_id}`}
                  className="text-lg font-semibold text-primary-text hover:underline"
                >
                  {jobResult.company_name}
                </Link>
                {jobResult.company_domain && (
                  <span className="text-sm text-muted-foreground">
                    {jobResult.company_domain}
                  </span>
                )}
                <Badge variant={jobResult.company_created ? "secondary" : "outline"}>
                  {jobResult.company_created ? "New company" : "Existing company"}
                </Badge>
              </div>
              {qualificationResults && (
                <QualificationResultsTable results={qualificationResults} />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
