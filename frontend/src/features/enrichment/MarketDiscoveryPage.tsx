import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPost } from "@/api/client";
import type {
  MarketDiscoveryConfirmRequest,
  MarketDiscoveryParsed,
  MarketDiscoveryRun,
  MarketDiscoveryStarted,
  JobStatus,
  QualificationCriterionList,
} from "@/api/types";
import { CouldNotDetermineBadge } from "@/components/StatusBadge";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const POLL_INTERVAL_MS = 1500;

type BulkQualifyResult = {
  qualified: number;
  not_qualified: number;
  could_not_determine: number;
  errors: { company_id: string; error: string }[];
};

export function MarketDiscoveryPage() {
  const [rawInput, setRawInput] = useState("");
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [runId, setRunId] = useState<string | null>(null);
  const [industryKeywords, setIndustryKeywords] = useState("");
  const [location, setLocation] = useState("");
  const [employeeSizeRange, setEmployeeSizeRange] = useState("");
  const [confidence, setConfidence] = useState<{
    industry_keywords: string;
    location: string;
    employee_size_range: string;
  } | null>(null);

  const [confirming, setConfirming] = useState(false);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [run, setRun] = useState<MarketDiscoveryRun | null>(null);
  const pollRef = useRef<number | null>(null);

  const [activeCriteriaCount, setActiveCriteriaCount] = useState<number | null>(null);
  const [qualifying, setQualifying] = useState(false);
  const [qualifyError, setQualifyError] = useState<string | null>(null);
  const [qualifyJob, setQualifyJob] = useState<JobStatus | null>(null);
  const qualifyPollRef = useRef<number | null>(null);

  useEffect(() => {
    apiGet<QualificationCriterionList>("/qualification/criteria")
      .then((list) => setActiveCriteriaCount(list.items.filter((c) => c.is_active).length))
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      if (qualifyPollRef.current) window.clearInterval(qualifyPollRef.current);
    };
  }, []);

  async function handleParse(e: FormEvent) {
    e.preventDefault();
    if (!rawInput.trim()) return;
    setError(null);
    setParsing(true);
    setJob(null);
    setRun(null);
    try {
      const parsed = await apiPost<MarketDiscoveryParsed>("/market-discovery/parse", {
        raw_input: rawInput,
      });
      setRunId(parsed.ingestion_run_id);
      setIndustryKeywords(parsed.parsed_fields.industry_keywords.value.join(", "));
      setLocation(parsed.parsed_fields.location.value ?? "");
      setEmployeeSizeRange(parsed.parsed_fields.employee_size_range.value ?? "");
      setConfidence({
        industry_keywords: parsed.parsed_fields.industry_keywords.confidence,
        location: parsed.parsed_fields.location.confidence,
        employee_size_range: parsed.parsed_fields.employee_size_range.confidence,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to parse market description");
    } finally {
      setParsing(false);
    }
  }

  async function handleConfirm() {
    if (!runId) return;
    setError(null);
    setConfirming(true);
    try {
      const body: MarketDiscoveryConfirmRequest = {
        industry_keywords: industryKeywords
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        location: location.trim() || null,
        employee_size_range: employeeSizeRange.trim() || null,
      };
      const started = await apiPost<MarketDiscoveryStarted>(
        `/market-discovery/${runId}/confirm`,
        body,
      );
      pollRef.current = window.setInterval(async () => {
        const status = await apiGet<JobStatus>(`/jobs/${started.job_id}`);
        setJob(status);
        if (status.status === "done" || status.status === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          const finishedRun = await apiGet<MarketDiscoveryRun>(`/market-discovery/${runId}`);
          setRun(finishedRun);
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to start discovery");
    } finally {
      setConfirming(false);
    }
  }

  async function handleQualifyRunCompanies() {
    if (!runId) return;
    setQualifyError(null);
    setQualifying(true);
    setQualifyJob(null);
    try {
      const started = await apiPost<MarketDiscoveryStarted>(
        `/market-discovery/${runId}/qualify-companies`,
      );
      qualifyPollRef.current = window.setInterval(async () => {
        const status = await apiGet<JobStatus>(`/jobs/${started.job_id}`);
        setQualifyJob(status);
        if (status.status === "done" || status.status === "failed") {
          if (qualifyPollRef.current) window.clearInterval(qualifyPollRef.current);
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setQualifyError(err instanceof Error ? err.message : "failed to start qualification");
    } finally {
      setQualifying(false);
    }
  }

  const showConfirmForm = runId !== null && !job;
  const qualifyResult = (qualifyJob?.result as unknown as BulkQualifyResult | null) ?? null;

  return (
    <div>
      <PageHeader
        eyebrow="Enrichment"
        title="Market Discovery"
        description='Describe a target market in plain text — e.g. "SaaS companies in Bangalore, 50-200 employees" — and confirm the parsed interpretation before any scraping runs.'
      />

      <Card>
        <CardContent>
          <form onSubmit={handleParse} className="flex flex-col gap-3">
            <Textarea
              value={rawInput}
              onChange={(e) => setRawInput(e.target.value)}
              placeholder="e.g. SaaS companies in Bangalore, 50-200 employees"
              rows={3}
            />
            <Button type="submit" disabled={!rawInput.trim() || parsing} className="self-start">
              {parsing ? "Parsing…" : "Parse"}
            </Button>
          </form>
          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {showConfirmForm && confidence && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg font-bold">Confirm interpretation</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted-foreground">
              Correct anything that's wrong before starting the search — fields marked "could not
              determine" were left blank, not guessed.
            </p>

            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="industry-keywords" className="flex items-center gap-2">
                  Industry keywords (comma-separated)
                  {confidence.industry_keywords === "could_not_determine" && (
                    <CouldNotDetermineBadge />
                  )}
                </Label>
                <Input
                  id="industry-keywords"
                  type="text"
                  value={industryKeywords}
                  onChange={(e) => setIndustryKeywords(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="location" className="flex items-center gap-2">
                  Location
                  {confidence.location === "could_not_determine" && <CouldNotDetermineBadge />}
                </Label>
                <Input
                  id="location"
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="employee-size-range" className="flex items-center gap-2">
                  Employee size range
                  {confidence.employee_size_range === "could_not_determine" && (
                    <CouldNotDetermineBadge />
                  )}
                </Label>
                <Input
                  id="employee-size-range"
                  type="text"
                  value={employeeSizeRange}
                  onChange={(e) => setEmployeeSizeRange(e.target.value)}
                />
              </div>
            </div>

            <Button type="button" onClick={handleConfirm} disabled={confirming} className="mt-6">
              {confirming ? "Starting…" : "Confirm & Start Discovery"}
            </Button>
          </CardContent>
        </Card>
      )}

      {job && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg font-bold">Discovery status: {job.status}</CardTitle>
          </CardHeader>
          <CardContent>
            {job.status === "running" && job.progress && (
              <p className="text-sm text-muted-foreground">
                Processed {job.progress.done} of {job.progress.total} candidates…
              </p>
            )}
            {job.status === "failed" && <p className="text-sm text-destructive">{job.error}</p>}
            {run?.summary && (
              <ul className="mt-2 list-inside list-disc text-sm">
                <li>Candidates found: {run.summary.candidates_found}</li>
                <li>New companies created: {run.summary.companies_created}</li>
              </ul>
            )}
            {job.status === "done" && (
              <p className="mt-3 text-sm">
                <Link to="/companies" className="text-primary-text hover:underline">
                  View companies →
                </Link>{" "}
                or{" "}
                <Link to="/needs-review" className="text-primary-text hover:underline">
                  check Needs Review →
                </Link>
              </p>
            )}

            {job.status === "done" && run?.summary && run.summary.companies_created > 0 && (
              <div className="mt-4 border-t border-border pt-4">
                <Button
                  type="button"
                  size="sm"
                  onClick={handleQualifyRunCompanies}
                  disabled={qualifying || activeCriteriaCount === 0 || !!qualifyJob}
                >
                  {qualifying
                    ? "Starting…"
                    : `Qualify ${run.summary.companies_created} new companies`}
                </Button>
                {activeCriteriaCount === 0 && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    No active qualification criteria yet —{" "}
                    <Link
                      to="/qualification/criteria/new"
                      className="text-primary-text hover:underline"
                    >
                      add one
                    </Link>{" "}
                    before qualifying.
                  </p>
                )}
                {qualifyError && (
                  <p className="mt-2 text-sm text-destructive">{qualifyError}</p>
                )}
                {qualifyJob && (
                  <div className="mt-2 text-sm">
                    {qualifyJob.status === "running" && qualifyJob.progress && (
                      <p className="text-muted-foreground">
                        Qualifying {qualifyJob.progress.done} of {qualifyJob.progress.total}…
                      </p>
                    )}
                    {qualifyJob.status === "failed" && (
                      <p className="text-destructive">{qualifyJob.error}</p>
                    )}
                    {qualifyJob.status === "done" && qualifyResult && (
                      <>
                        <ul className="list-inside list-disc">
                          <li>Qualified: {qualifyResult.qualified}</li>
                          <li>Not qualified: {qualifyResult.not_qualified}</li>
                          <li>Could not determine: {qualifyResult.could_not_determine}</li>
                          {qualifyResult.errors.length > 0 && (
                            <li className="text-destructive">
                              Failed: {qualifyResult.errors.length}
                            </li>
                          )}
                        </ul>
                        <Link to="/companies" className="text-primary-text hover:underline">
                          View companies →
                        </Link>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
