import {
  ChevronDown,
  ListChecks,
  Loader2,
  MessageSquareText,
  Search,
  Send,
  Sparkles,
} from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

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
  RoleCategory,
  RoleCategoryList,
} from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { CouldNotDetermineBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { InfoTip } from "@/components/InfoTip";
import { ProductMultiSelect } from "@/components/ProductMultiSelect";
import { RoleCategoryMultiSelect } from "@/components/RoleCategoryMultiSelect";
import { FormSection } from "@/components/FormSection";
import { MarketFitRequirements } from "@/features/enrichment/MarketFitRequirements";
import {
  seedRequirements,
  toRequestCriteria,
  type Requirement,
} from "@/features/enrichment/runCriteria";
import { RunOutcome } from "@/features/enrichment/RunOutcome";
import { RunProgress } from "@/features/enrichment/RunProgress";
import { RunWorklist } from "@/features/enrichment/RunWorklist";
import { usePersistentState } from "@/lib/usePersistentState";
import { jobStatusLabel } from "@/lib/format";

const POLL_INTERVAL_MS = 1500;

type BulkQualifyResult = {
  qualified: number;
  not_qualified: number;
  could_not_determine: number;
  not_checked?: number;
  errors: { company_id: string; error: string }[];
};

export function MarketDiscoveryPage() {
  // Inputs and ids are remembered across page switches (see usePersistentState); the job and run
  // themselves are re-fetched from the server by id, so a finished run's results are still here
  // when you come back, and a run still in progress keeps updating.
  const [rawInput, setRawInput] = usePersistentState("md.rawInput", "");
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [runId, setRunId] = usePersistentState<string | null>("md.runId", null);
  const [jobId, setJobId] = usePersistentState<string | null>("md.jobId", null);
  const [industryKeywords, setIndustryKeywords] = usePersistentState(
    "md.industryKeywords",
    "",
  );
  const [location, setLocation] = usePersistentState("md.location", "");
  const [employeeSizeRange, setEmployeeSizeRange] = usePersistentState(
    "md.employeeSize",
    "",
  );
  const [requirements, setRequirements] = usePersistentState<Requirement[]>(
    "md.criteria.typed",
    [],
  );
  const [confidence, setConfidence] = usePersistentState<{
    industry_keywords: string;
    location: string;
    employee_size_range: string;
  } | null>("md.confidence", null);

  // A prompt handed over from the dashboard's search box (router state). Consumed once.
  const routerLocation = useLocation();
  const navigate = useNavigate();
  const handoffPrompt =
    (routerLocation.state as { prompt?: string } | null)?.prompt ?? null;
  const handoffStarted = useRef(false);
  const [handoffNotice, setHandoffNotice] = useState<string | null>(null);

  const [confirming, setConfirming] = useState(false);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [run, setRun] = useState<MarketDiscoveryRun | null>(null);
  const pollRef = useRef<number | null>(null);

  const [qualifying, setQualifying] = useState(false);
  // How many companies the worklist shows as ready and as left out, for the finished summary.
  const [worklistCounts, setWorklistCounts] = useState<{
    runId: string;
    ready: number;
    notShown: number;
  } | null>(null);
  const [qualifyError, setQualifyError] = useState<string | null>(null);
  const [qualifyJob, setQualifyJob] = useState<JobStatus | null>(null);
  const qualifyPollRef = useRef<number | null>(null);

  const [activeRoleCategoryCount, setActiveRoleCategoryCount] = useState<
    number | null
  >(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [roleCategories, setRoleCategories] = useState<RoleCategory[]>([]);
  const [selectedRoleCategoryIds, setSelectedRoleCategoryIds] =
    usePersistentState<string[]>("md.roleCategoryIds", []);
  const [selectedProductIds, setSelectedProductIds] = usePersistentState<
    string[]
  >("md.productIds", []);

  // Poll a pipeline job until it finishes, then load the finished run. Used both when a run is
  // confirmed and when returning to the page while one is still going.
  function startPolling(pollJobId: string, forRunId: string) {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const status = await apiGet<JobStatus>(`/jobs/${pollJobId}`);
        setJob(status);
        if (status.status === "done" || status.status === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          const finishedRun = await apiGet<MarketDiscoveryRun>(
            `/market-discovery/${forRunId}`,
          );
          setRun(finishedRun);
        }
      } catch {
        // One failed poll (a blip, a restart) must not end the loop — the next tick retries.
      }
    }, POLL_INTERVAL_MS);
  }

  function resetSearch() {
    if (pollRef.current) window.clearInterval(pollRef.current);
    setRawInput("");
    setRunId(null);
    setJobId(null);
    setIndustryKeywords("");
    setLocation("");
    setEmployeeSizeRange("");
    setRequirements([]);
    setConfidence(null);
    // Product selection is remembered across searches like every other field here — without
    // clearing it, an offering checked for one run (e.g. the SAP one) silently carries into the
    // next, unrelated one.
    setSelectedProductIds([]);
    setSelectedRoleCategoryIds([]);
    setJob(null);
    setRun(null);
    setError(null);
  }

  // Restore a remembered run from the server (finished -> its results; still going -> keep polling).
  async function restoreRun(
    restoreJobId: string,
    restoreRunId: string,
    isCancelled: () => boolean,
  ) {
    try {
      const status = await apiGet<JobStatus>(`/jobs/${restoreJobId}`);
      if (isCancelled()) return;
      setJob(status);
      if (status.status === "done" || status.status === "failed") {
        const finishedRun = await apiGet<MarketDiscoveryRun>(
          `/market-discovery/${restoreRunId}`,
        );
        if (!isCancelled()) setRun(finishedRun);
      } else {
        startPolling(restoreJobId, restoreRunId);
      }
    } catch {
      // The remembered job no longer exists (e.g. the database was wiped): start clean rather
      // than show a confirm form for a run that can't be resumed.
      if (!isCancelled()) resetSearch();
    }
  }

  // Coming back to the page: restore the last run from the server. When the dashboard handed over
  // a prompt, the effect below decides instead (a running search is restored, anything else is
  // replaced by the new search).
  useEffect(() => {
    if (handoffPrompt || !jobId || !runId) return;
    let cancelled = false;
    void restoreRun(jobId, runId, () => cancelled);
    return () => {
      cancelled = true;
    };
    // Runs once on mount, deliberately: it only restores what was remembered.
  }, []);

  // Arriving from the dashboard with a typed prompt: start that search (parse it and show the
  // confirm step). A run that is still going is never replaced: the prompt is parked and the
  // running one stays on screen. Guarded by a ref so React StrictMode cannot parse twice.
  useEffect(() => {
    if (!handoffPrompt || handoffStarted.current) return;
    handoffStarted.current = true;
    navigate(".", { replace: true, state: null }); // do not run again on refresh
    void (async () => {
      if (jobId && runId) {
        try {
          const status = await apiGet<JobStatus>(`/jobs/${jobId}`);
          if (status.status === "pending" || status.status === "running") {
            setHandoffNotice(handoffPrompt);
            await restoreRun(jobId, runId, () => false);
            return;
          }
        } catch {
          // the remembered job is gone; start the new search below
        }
      }
      resetSearch();
      setRawInput(handoffPrompt);
      await parseText(handoffPrompt);
    })();
    // Runs once on mount: it only consumes what the dashboard handed over.
  }, []);

  useEffect(() => {
    apiGet<RoleCategoryList>("/role-categories")
      .then((list) => {
        const active = list.items.filter((c) => c.is_active);
        setActiveRoleCategoryCount(active.length);
        setRoleCategories(active);
      })
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
    apiGet<ProductList>("/products?limit=200")
      .then((list) => {
        setProducts(list.items);
        // Unambiguous default: exactly one product means there's nothing to choose between.
        if (list.items.length === 1) setSelectedProductIds([list.items[0].id]);
      })
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      if (qualifyPollRef.current) window.clearInterval(qualifyPollRef.current);
    };
  }, []);

  function handleParse(e: FormEvent) {
    e.preventDefault();
    void parseText(rawInput);
  }

  async function parseText(text: string) {
    if (!text.trim()) return;
    setError(null);
    setParsing(true);
    setJob(null);
    setJobId(null);
    setRun(null);
    try {
      const parsed = await apiPost<MarketDiscoveryParsed>(
        "/market-discovery/parse",
        {
          raw_input: text,
        },
      );
      setRunId(parsed.ingestion_run_id);
      setIndustryKeywords(
        parsed.parsed_fields.industry_keywords.value.join(", "),
      );
      setLocation(parsed.parsed_fields.location.value ?? "");
      setEmployeeSizeRange(
        parsed.parsed_fields.employee_size_range.value ?? "",
      );
      setRequirements(
        seedRequirements(
          parsed.parsed_fields.industry_keywords.value.join(", "),
          parsed.parsed_fields.location.value ?? "",
          parsed.parsed_fields.employee_size_range.value ?? "",
        ),
      );
      setConfidence({
        industry_keywords: parsed.parsed_fields.industry_keywords.confidence,
        location: parsed.parsed_fields.location.confidence,
        employee_size_range:
          parsed.parsed_fields.employee_size_range.confidence,
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "failed to parse market description",
      );
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
        product_ids: selectedProductIds,
        role_category_ids: selectedRoleCategoryIds,
        criteria: toRequestCriteria(requirements),
      };
      const started = await apiPost<MarketDiscoveryStarted>(
        `/market-discovery/${runId}/confirm`,
        body,
      );
      setJobId(started.job_id);
      startPolling(started.job_id, runId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "failed to start discovery",
      );
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
          if (qualifyPollRef.current)
            window.clearInterval(qualifyPollRef.current);
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setQualifyError(
        err instanceof Error ? err.message : "failed to start qualification",
      );
    } finally {
      setQualifying(false);
    }
  }

  // One line up front instead of a silently empty result: each later stage is skipped when its
  // prerequisite is missing.
  const missingSetup: string[] = [];
  if (activeRoleCategoryCount === 0)
    missingSetup.push("no active role categories");
  if (products !== null && products.length === 0)
    missingSetup.push("no offering to pitch");

  // Keyed on the remembered job id (not the fetched job) so the confirm form doesn't flash up
  // for a moment while a restored run's status is still loading.
  const showConfirmForm = runId !== null && !jobId;
  const runInProgress = job?.status === "pending" || job?.status === "running";
  // Covers every in-flight moment, not just "a job exists and is running" — parsing and
  // confirming are their own async windows before a job even exists, during which every other
  // action on this page should be inert too (clicking Parse again, Reset, or Confirm a second
  // time while the first request is still in flight used to all stay clickable).
  const busy = parsing || confirming || runInProgress;
  const qualifyResult =
    (qualifyJob?.result as unknown as BulkQualifyResult | null) ?? null;
  const pipelineResult =
    job?.status === "done"
      ? ((job.result as unknown as AutoPipelineResult | null) ?? null)
      : null;
  // The pipeline already ran qualification automatically unless it was skipped (e.g. no active
  // criteria existed yet at confirm time) — only offer the manual catch-up button in that case.
  const showManualQualifyButton =
    pipelineResult !== null && pipelineResult.qualification.ran !== true;

  return (
    <div>
      <PageHeader title="Market Discovery" />

      {missingSetup.length > 0 && (
        <p className="mb-4 rounded-md border border-chip-warning-fg/30 bg-chip-warning-bg px-4 py-2 text-sm text-chip-warning-fg">
          Before you run: {missingSetup.join("; ")}. Those stages will be
          skipped and the result will be empty.
        </p>
      )}

      {handoffNotice && (
        <Card className="mb-6 border-warning">
          <CardContent>
            <p className="text-sm">
              A search is still running, so the new one was not started: &ldquo;
              {handoffNotice}
              &rdquo;. When this run finishes, use &ldquo;Start a new
              search&rdquo; and paste it in.
            </p>
          </CardContent>
        </Card>
      )}

      <details className="group mb-6 border border-primary/30 bg-primary/5">
        <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
          <Sparkles
            className="size-5 shrink-0 text-primary"
            aria-hidden="true"
          />
          <span className="font-semibold">What this does</span>
          <span className="text-sm text-muted-foreground">
            New companies enter Sales Intelligence here.
          </span>
          <ChevronDown
            className="ml-auto size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>
        <ol className="flex list-decimal flex-col gap-1 px-5 pb-4 pl-12 text-sm text-muted-foreground">
          <li>Describe the companies you want to find, in your own words.</li>
          <li>
            We turn it into filters and show them to you. Change anything before
            the search starts.
          </li>
          <li>
            After you confirm, we find matching companies, check which ones are
            worth pursuing, find who to talk to, and prepare outreach drafts for
            you to review.
          </li>
        </ol>
      </details>

      <FormSection
        icon={MessageSquareText}
        title="Describe the companies you want"
        description="Write it the way you would say it: industry, place, size, anything else that matters."
      >
        <form onSubmit={handleParse} className="flex flex-col gap-3">
          <Textarea
            aria-label="Describe the companies you want to find"
            value={rawInput}
            onChange={(e) => setRawInput(e.target.value)}
            placeholder="e.g. SaaS companies in Bangalore, 50-200 employees"
            rows={3}
            disabled={busy}
          />
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={!rawInput.trim() || busy}>
              {parsing ? "Parsing…" : "Parse"}
            </Button>
            {(rawInput || runId || job) && !busy && (
              <Button type="button" variant="outline" onClick={resetSearch}>
                Reset
              </Button>
            )}
          </div>
          {runInProgress && (
            <p className="text-xs text-muted-foreground">
              A search is still running. You can start a new one when it
              finishes.
            </p>
          )}
        </form>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </FormSection>

      {showConfirmForm && confidence && (
        <section
          aria-label="Confirm your search"
          className="mt-6 flex flex-col gap-5"
        >
          <div>
            <h2 className="text-xl font-bold">Check your search</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              We filled this in from what you typed. Fix anything that is off,
              then start.
            </p>
          </div>

          <FormSection
            icon={Search}
            title="Your search details"
            description="This is what we understood from your description. Change anything that is wrong, or leave a field empty to not filter on it."
          >
            <div className="flex flex-col gap-1.5">
              <Label
                htmlFor="industry-keywords"
                className="flex items-center gap-2"
              >
                Industry
                {confidence.industry_keywords === "could_not_determine" && (
                  <CouldNotDetermineBadge />
                )}
              </Label>
              <Input
                id="industry-keywords"
                type="text"
                value={industryKeywords}
                placeholder="e.g. healthcare, logistics"
                onChange={(e) => setIndustryKeywords(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Separate several with commas.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="location" className="flex items-center gap-2">
                  Where
                  {confidence.location === "could_not_determine" && (
                    <CouldNotDetermineBadge />
                  )}
                </Label>
                <Input
                  id="location"
                  type="text"
                  value={location}
                  placeholder="City, country or region"
                  onChange={(e) => setLocation(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label
                  htmlFor="employee-size-range"
                  className="flex items-center gap-2"
                >
                  Company size
                  {confidence.employee_size_range === "could_not_determine" && (
                    <CouldNotDetermineBadge />
                  )}
                </Label>
                <Input
                  id="employee-size-range"
                  type="text"
                  value={employeeSizeRange}
                  placeholder="e.g. 500-2000 or 5000+"
                  onChange={(e) => setEmployeeSizeRange(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Number of employees.
                </p>
              </div>
            </div>
          </FormSection>

          <FormSection
            icon={ListChecks}
            title="Checks for every company"
            optional
            description="Optional. Each company is checked against these and keeps them on its page. Mark a check as must have to drop companies that clearly fail it."
          >
            <MarketFitRequirements
              value={requirements}
              onChange={setRequirements}
            />
          </FormSection>

          <FormSection
            icon={Send}
            title="Offerings and people to focus on"
            optional
            description="Not needed to find companies. Choose these if you want fit checks and drafts built around specific offerings and roles."
          >
            <div className="flex flex-col gap-1.5">
              <Label>Offerings to pitch</Label>
              {products && products.length > 1 && (
                <ProductMultiSelect
                  products={products}
                  selectedIds={new Set(selectedProductIds)}
                  onToggle={(productId) =>
                    setSelectedProductIds((current) =>
                      current.includes(productId)
                        ? current.filter((id) => id !== productId)
                        : [...current, productId],
                    )
                  }
                />
              )}
              <p className="text-xs text-muted-foreground">
                {selectedProductIds.length === 0
                  ? products && products.length === 0
                    ? "No offerings added yet. Add them under Offerings to get fit checks and drafts."
                    : "Nothing chosen yet. You can still write a draft for any company later."
                  : selectedProductIds.length === 1
                    ? "We check how well it fits each company and write drafts around it."
                    : "Each offering is checked against every company. Each draft pitches the one that fits that company best."}
              </p>
            </div>
            {roleCategories.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <Label className="flex items-center gap-2">
                  People to focus on
                  <InfoTip label="About people to focus on">
                    Leave this on all roles to look at everyone. Pick roles only
                    if you want this search to concentrate on them; you still
                    choose which contacts to confirm.
                  </InfoTip>
                </Label>
                <RoleCategoryMultiSelect
                  categories={roleCategories}
                  selectedIds={new Set(selectedRoleCategoryIds)}
                  onToggle={(categoryId) =>
                    setSelectedRoleCategoryIds((current) =>
                      current.includes(categoryId)
                        ? current.filter((id) => id !== categoryId)
                        : [...current, categoryId],
                    )
                  }
                />
              </div>
            )}
          </FormSection>

          <div className="flex flex-wrap items-center justify-between gap-4 border border-border bg-card px-5 py-4 shadow-xs">
            <p className="max-w-xl text-sm text-muted-foreground">
              The search runs in the background, so you can keep using the app.
              Progress shows below once it starts.
            </p>
            <Button
              type="button"
              size="lg"
              onClick={handleConfirm}
              disabled={busy}
              className="min-w-44"
            >
              {confirming ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <Search aria-hidden="true" />
              )}
              {confirming ? "Starting…" : "Start the search"}
            </Button>
          </div>
        </section>
      )}

      {job && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg font-bold">
              {runInProgress && (
                <Loader2 className="size-4 animate-spin text-primary motion-reduce:animate-none" />
              )}
              {runInProgress
                ? "Working on your search"
                : job.status === "done"
                  ? "Search complete"
                  : `Progress: ${jobStatusLabel(job.status)}`}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {(job.status === "running" || job.status === "pending") && (
              <RunProgress job={job} />
            )}
            {job.status === "failed" && (
              <p className="text-sm text-destructive">{job.error}</p>
            )}
            {job.status === "done" && run?.summary && (
              <RunOutcome
                outcome={{
                  found: run.summary.candidates_found,
                  fit: pipelineResult?.qualification.ran
                    ? pipelineResult.qualification.qualified +
                      pipelineResult.qualification.could_not_determine +
                      (pipelineResult.qualification.not_checked ?? 0)
                    : null,
                  sorted: pipelineResult?.role_classification.ran
                    ? pipelineResult.role_classification.companies_classified
                    : null,
                  ready:
                    worklistCounts?.runId === runId
                      ? worklistCounts.ready
                      : null,
                  needAttention:
                    worklistCounts?.runId === runId
                      ? worklistCounts.notShown
                      : null,
                }}
                cappedAt={
                  pipelineResult?.capped
                    ? (pipelineResult.ranking?.top.length ?? null)
                    : null
                }
                onReview={() =>
                  document
                    .getElementById("run-worklist")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" })
                }
                onNewSearch={resetSearch}
              />
            )}
            {run?.error && (
              <p className="mt-2 text-sm text-destructive">{run.error}</p>
            )}

            {job.status === "done" &&
              run?.summary?.candidates_found === 0 &&
              (run.summary.raw_results ?? 0) > 0 && (
                <div className="mt-3 border border-chip-warning-fg bg-chip-warning-bg p-3 text-sm text-chip-warning-fg">
                  <p>
                    No real companies were found — the search mostly returned
                    general articles or pages, not a company directory. Try
                    naming a more specific company-type noun (e.g. "vendors",
                    "providers", "operators") instead of a broad topic phrase.
                  </p>
                  {run.summary.rejected_samples &&
                    run.summary.rejected_samples.length > 0 && (
                      <>
                        <p className="mt-2 font-semibold">
                          Examples of what was rejected:
                        </p>
                        <ul className="mt-1 list-inside list-disc">
                          {run.summary.rejected_samples.map((sample, i) => (
                            <li key={i}>
                              <strong>{sample.name}</strong> —{" "}
                              {sample.reasoning}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                </div>
              )}

            {(pipelineResult || run?.summary?.enrichment) && (
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer text-muted-foreground">
                  Run details
                </summary>
                {run?.summary?.raw_results != null && (
                  <p className="mt-2 text-muted-foreground">
                    Search funnel: {run.summary.raw_results} raw result
                    {run.summary.raw_results === 1 ? "" : "s"} →{" "}
                    {run.summary.extracted ?? 0} extracted →{" "}
                    {run.summary.accepted ?? 0} accepted as real companies
                    {(run.summary.rejected ?? 0) > 0 &&
                      ` (${run.summary.rejected} rejected)`}
                  </p>
                )}
                {run?.summary?.context_dev && (
                  <p className="mt-2 text-muted-foreground">
                    context.dev: {run.summary.context_dev.credits_used} of{" "}
                    {run.summary.context_dev.credit_ceiling} credits used
                    {run.summary.context_dev.skipped_sufficient != null &&
                      ` · ${run.summary.context_dev.skipped_sufficient} companies needed no paid lookup`}
                    {run.summary.context_dev.budget_exhausted &&
                      " · credit ceiling reached, later companies used scraper data only"}
                  </p>
                )}
                {run?.summary?.enrichment && (
                  <p className="mt-2 text-muted-foreground">
                    Company data source:{" "}
                    {run.summary.company_data_source ?? "unknown"} · enriched{" "}
                    {run.summary.enrichment.enriched}, failed{" "}
                    {run.summary.enrichment.failed}, industry filled{" "}
                    {run.summary.enrichment.industry_filled}
                    {Object.keys(run.summary.enrichment.branch_errors ?? {})
                      .length > 0 &&
                      ` · provider errors: ${Object.entries(
                        run.summary.enrichment.branch_errors ?? {},
                      )
                        .map(([branch, n]) => `${branch} ${n}`)
                        .join(", ")}`}
                    {Object.keys(run.summary.enrichment.by_source).length > 0 &&
                      ` · by source: ${Object.entries(
                        run.summary.enrichment.by_source,
                      )
                        .map(([source, n]) => `${source} ${n}`)
                        .join(", ")}`}
                  </p>
                )}
                {pipelineResult && (
                  <div className="mt-3 flex flex-col gap-3 text-sm">
                    <div>
                      <p className="font-semibold">Qualification</p>
                      {pipelineResult.qualification.ran ? (
                        <ul className="list-inside list-disc text-muted-foreground">
                          <li>
                            Qualified: {pipelineResult.qualification.qualified}
                          </li>
                          <li>
                            Not qualified:{" "}
                            {pipelineResult.qualification.not_qualified}
                          </li>
                          <li>
                            Needs evidence (could not be verified):{" "}
                            {pipelineResult.qualification.could_not_determine}
                          </li>
                          {(pipelineResult.qualification.not_checked ?? 0) >
                            0 && (
                            <li>
                              Not checked (no criteria chosen):{" "}
                              {pipelineResult.qualification.not_checked}
                            </li>
                          )}
                        </ul>
                      ) : (
                        <p className="text-muted-foreground">
                          Skipped —{" "}
                          {pipelineResult.qualification.skipped_reason}
                        </p>
                      )}
                    </div>
                    {pipelineResult.ranking && (
                      <div>
                        <p className="font-semibold">Ranking</p>
                        <p className="text-muted-foreground">
                          {pipelineResult.ranking.ranked} companies scored by
                          Priority Score; the top{" "}
                          {pipelineResult.ranking.top.length} went on to role
                          classification.
                        </p>
                      </div>
                    )}
                    <div>
                      <p className="font-semibold">Role classification</p>
                      {pipelineResult.role_classification.ran ? (
                        <p className="text-muted-foreground">
                          Companies classified:{" "}
                          {
                            pipelineResult.role_classification
                              .companies_classified
                          }
                        </p>
                      ) : (
                        <p className="text-muted-foreground">
                          Skipped —{" "}
                          {pipelineResult.role_classification.skipped_reason}
                        </p>
                      )}
                    </div>
                    <div>
                      <p className="font-semibold">Drafting</p>
                      {pipelineResult.drafting.ran ? (
                        <p className="text-muted-foreground">
                          Drafts generated:{" "}
                          {pipelineResult.drafting.drafts_generated}
                        </p>
                      ) : (
                        <p className="text-muted-foreground">
                          Skipped — {pipelineResult.drafting.skipped_reason}
                        </p>
                      )}
                    </div>
                    {pipelineResult.capped && (
                      <p className="text-xs text-muted-foreground">
                        More companies qualified than this run's automatic cap
                        allows through to role classification and drafting — the
                        rest are qualified only; classify/draft them
                        individually from their company pages if needed.
                      </p>
                    )}
                  </div>
                )}
              </details>
            )}

            {job.status === "failed" && (
              <Button
                type="button"
                variant="action"
                className="mt-3"
                onClick={resetSearch}
              >
                Start a new search
              </Button>
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
                    disabled={qualifying || !!qualifyJob}
                  >
                    {qualifying
                      ? "Starting…"
                      : `Qualify ${run.summary.companies_created} new companies`}
                  </Button>
                  {qualifyError && (
                    <p className="mt-2 text-sm text-destructive">
                      {qualifyError}
                    </p>
                  )}
                  {qualifyJob && (
                    <div className="mt-2 text-sm">
                      {qualifyJob.status === "running" &&
                        qualifyJob.progress && (
                          <p className="text-muted-foreground">
                            Qualifying {qualifyJob.progress.done} of{" "}
                            {qualifyJob.progress.total}…
                          </p>
                        )}
                      {qualifyJob.status === "failed" && (
                        <p className="text-destructive">{qualifyJob.error}</p>
                      )}
                      {qualifyJob.status === "done" && qualifyResult && (
                        <>
                          <ul className="list-inside list-disc">
                            <li>Qualified: {qualifyResult.qualified}</li>
                            <li>
                              Not qualified: {qualifyResult.not_qualified}
                            </li>
                            <li>
                              Could not determine:{" "}
                              {qualifyResult.could_not_determine}
                            </li>
                            {qualifyResult.errors.length > 0 && (
                              <li className="text-destructive">
                                Failed: {qualifyResult.errors.length}
                              </li>
                            )}
                          </ul>
                          <Link
                            to="/companies"
                            className="text-primary-text hover:underline"
                          >
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

      {job && runId && (
        <RunWorklist
          runId={runId}
          // RunWorklist's own per-contact "write draft" button still sends exactly one product —
          // only pass one through when the rep's selection for this run is unambiguous;
          // otherwise its existing "choose an offering above" messaging covers the rest.
          productId={
            selectedProductIds.length === 1 ? selectedProductIds[0] : null
          }
          live={job.status === "running" || job.status === "pending"}
          onSummary={(ready, notShown) =>
            setWorklistCounts((previous) =>
              previous?.runId === runId &&
              previous.ready === ready &&
              previous.notShown === notShown
                ? previous
                : { runId, ready, notShown },
            )
          }
        />
      )}
    </div>
  );
}
