import { Loader2, Sparkles } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPost } from "@/api/client";
import type {
  AutoPipelineResult,
  MarketDiscoveryConfirmRequest,
  MarketDiscoveryParsed,
  MarketDiscoveryRun,
  MarketDiscoveryStarted,
  JobStatus,
  Product,
  ProductList,
  QualificationCriterionList,
} from "@/api/types";
import { CouldNotDetermineBadge } from "@/components/StatusBadge";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

  const [products, setProducts] = useState<Product[] | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string>("");

  useEffect(() => {
    apiGet<QualificationCriterionList>("/qualification/criteria")
      .then((list) => setActiveCriteriaCount(list.items.filter((c) => c.is_active).length))
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
    apiGet<ProductList>("/products")
      .then((list) => {
        setProducts(list.items);
        // Unambiguous default: exactly one product means there's nothing to choose between.
        if (list.items.length === 1) setSelectedProductId(list.items[0].id);
      })
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
        product_id: selectedProductId || null,
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
  const pipelineResult =
    job?.status === "done" ? ((job.result as unknown as AutoPipelineResult | null) ?? null) : null;
  // The pipeline already ran qualification automatically unless it was skipped (e.g. no active
  // criteria existed yet at confirm time) — only offer the manual catch-up button in that case.
  const showManualQualifyButton =
    pipelineResult !== null && pipelineResult.qualification.ran !== true;

  return (
    <div>
      <PageHeader
        eyebrow="Enrichment"
        title="Market Discovery"
        description='Describe a target market in plain text — e.g. "SaaS companies in Bangalore, 50-200 employees" — and confirm the parsed interpretation before any scraping runs.'
      />

      <Card className="mb-6 border-primary/30 bg-primary/5">
        <CardContent>
          <div className="flex items-start gap-3">
            <Sparkles className="mt-0.5 size-5 shrink-0 text-primary" />
            <div>
              <p className="font-semibold">What this does</p>
              <p className="mt-1 text-sm text-muted-foreground">
                This is how new companies enter Sales Intelligence — the whole prospecting engine
                starts here.
              </p>
              <ol className="mt-3 flex list-decimal flex-col gap-1 pl-5 text-sm text-muted-foreground">
                <li>You describe the market you're targeting, in plain English.</li>
                <li>
                  We parse it into structured filters and show you exactly what we understood —
                  you correct anything before any search runs.
                </li>
                <li>
                  Once you confirm, we automatically search for matching companies, judge whether
                  each one is worth pursuing, figure out who to talk to there, and draft outreach
                  messages ready for your review.
                </li>
              </ol>
            </div>
          </div>
        </CardContent>
      </Card>

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
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pipeline-product">Product to pitch (for automatic drafting)</Label>
                <Select value={selectedProductId} onValueChange={setSelectedProductId}>
                  <SelectTrigger id="pipeline-product" className="h-9 bg-card">
                    <SelectValue placeholder="No product selected" />
                  </SelectTrigger>
                  <SelectContent>
                    {(products ?? []).map((product) => (
                      <SelectItem key={product.id} value={product.id}>
                        {product.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!selectedProductId && (
                  <p className="text-xs text-muted-foreground">
                    {products && products.length === 0
                      ? "No products configured yet — discovery, qualification, and role classification will still run automatically, but drafting will be skipped."
                      : "Leaving this unselected skips automatic drafting — discovery, qualification, and role classification still run."}
                  </p>
                )}
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
            <CardTitle className="flex items-center gap-2 text-lg font-bold">
              {job.status === "running" && <Loader2 className="size-4 animate-spin text-primary" />}
              Pipeline status: {job.status}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {job.status === "running" && job.progress && (
              <p className="text-sm text-muted-foreground">
                Stage {job.progress.done} of {job.progress.total}
                {job.progress.done === 1 &&
                  " — searching the web for companies matching your target market"}
                {job.progress.done === 2 &&
                  " — checking which companies are a good fit for your product"}
                {job.progress.done === 3 && " — figuring out who at each company to talk to"}
                {job.progress.done === 4 && " — writing draft outreach messages for you to review"}
              </p>
            )}
            {job.status === "failed" && <p className="text-sm text-destructive">{job.error}</p>}
            {run?.summary && (
              <ul className="mt-2 list-inside list-disc text-sm">
                <li>Candidates found: {run.summary.candidates_found}</li>
                <li>New companies created: {run.summary.companies_created}</li>
              </ul>
            )}

            {pipelineResult && (
              <div className="mt-3 flex flex-col gap-3 text-sm">
                <div>
                  <p className="font-semibold">Qualification</p>
                  {pipelineResult.qualification.ran ? (
                    <ul className="list-inside list-disc text-muted-foreground">
                      <li>Qualified: {pipelineResult.qualification.qualified}</li>
                      <li>Not qualified: {pipelineResult.qualification.not_qualified}</li>
                      <li>
                        Could not determine: {pipelineResult.qualification.could_not_determine}
                      </li>
                    </ul>
                  ) : (
                    <p className="text-muted-foreground">
                      Skipped — {pipelineResult.qualification.skipped_reason}
                    </p>
                  )}
                </div>
                <div>
                  <p className="font-semibold">Role classification</p>
                  {pipelineResult.role_classification.ran ? (
                    <p className="text-muted-foreground">
                      Companies classified: {pipelineResult.role_classification.companies_classified}
                    </p>
                  ) : (
                    <p className="text-muted-foreground">
                      Skipped — {pipelineResult.role_classification.skipped_reason}
                    </p>
                  )}
                </div>
                <div>
                  <p className="font-semibold">Drafting</p>
                  {pipelineResult.drafting.ran ? (
                    <p className="text-muted-foreground">
                      Drafts generated: {pipelineResult.drafting.drafts_generated}
                    </p>
                  ) : (
                    <p className="text-muted-foreground">
                      Skipped — {pipelineResult.drafting.skipped_reason}
                    </p>
                  )}
                </div>
                {pipelineResult.capped && (
                  <p className="text-xs text-muted-foreground">
                    More companies qualified than this run's automatic cap allows through to role
                    classification and drafting — the rest are qualified only; classify/draft them
                    individually from their company pages if needed.
                  </p>
                )}
              </div>
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

            {job.status === "done" &&
              run?.summary &&
              run.summary.companies_created > 0 &&
              showManualQualifyButton && (
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
