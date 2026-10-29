import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Circle, Loader2 } from "lucide-react";

import { WebsiteLink } from "@/components/WebsiteLink";

import { apiGet, apiPost } from "@/api/client";
import type {
  AdhocQualificationCheckRequest,
  JobStatus,
  QualificationResult,
  ScrapeJobStarted,
} from "@/api/types";
import { InfoTip } from "@/components/InfoTip";
import { QualificationResultsTable } from "@/features/qualification/QualificationResultsTable";
import {
  elapsedLabel,
  quickCheckSteps,
  stepStates,
} from "@/features/qualification/quickCheckProgress";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { usePersistentState } from "@/lib/usePersistentState";

const POLL_INTERVAL_MS = 1500;

type AdhocQualifyJobResult = {
  company_id: string;
  company_name: string;
  company_domain: string | null;
  company_created: boolean;
  focus?: string | null;
};

type Finished = {
  result: AdhocQualifyJobResult;
  results: QualificationResult[];
};

// What was asked, kept with the job so the progress card can name it after a reload.
type Asked = { company: string; focus: string | null };

export function AdhocCheckPage() {
  // The form is remembered like the other search forms, and is never cleared by starting a check.
  const [company, setCompany] = usePersistentState("quickcheck.company", "");
  const [focus, setFocus] = usePersistentState("quickcheck.focus", "");
  const [asked, setAsked] = usePersistentState<Asked | null>(
    "quickcheck.asked",
    null,
  );
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  // Until the first poll answers, a check that was just started is treated as running.
  const [awaitingFirstPoll, setAwaitingFirstPoll] = useState(false);
  // The last finished check stays on screen while a new one runs, and is replaced when it is done.
  const [finished, setFinished] = useState<Finished | null>(null);
  // The last check's job id is remembered, so leaving this page and coming back still shows
  // its result (job and qualification results are re-fetched, never cached).
  const [jobId, setJobId] = usePersistentState<string | null>(
    "quickcheck.jobId",
    null,
  );
  const pollRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(Date.now());
  const [now, setNow] = useState(Date.now());

  // Follow a check job until it finishes, then load the company's qualification results.
  function track(trackedJobId: string) {
    if (pollRef.current) window.clearInterval(pollRef.current);
    async function poll() {
      try {
        const status = await apiGet<JobStatus>(`/jobs/${trackedJobId}`);
        setJob(status);
        setAwaitingFirstPoll(false);
        if (status.status === "done" || status.status === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          if (status.status === "done" && status.result) {
            const result = status.result as unknown as AdhocQualifyJobResult;
            const results = await apiGet<QualificationResult[]>(
              `/companies/${result.company_id}/qualification-results`,
            );
            setFinished({ result, results });
          }
        }
      } catch (err) {
        if (err instanceof Error && err.message.includes("404")) {
          // The job no longer exists (e.g. the database was wiped): stop and say so.
          if (pollRef.current) window.clearInterval(pollRef.current);
          setJobId(null);
          setAwaitingFirstPoll(false);
          setNotice("That check is no longer available. Start a new one.");
        }
        // Any other failed poll must not end the loop — the next tick retries.
      }
    }
    void poll();
    pollRef.current = window.setInterval(poll, POLL_INTERVAL_MS);
  }

  useEffect(() => {
    if (jobId) track(jobId);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
    // Runs once on mount, deliberately: it only restores what was remembered. A finished job is
    // simply polled once more, which loads its result.
  }, []);

  const running =
    awaitingFirstPoll || job?.status === "pending" || job?.status === "running";

  // A clock for the running check.
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const canSubmit = company.trim() !== "" && !running;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setNotice(null);
    setStarting(true);
    try {
      const body: AdhocQualificationCheckRequest = {
        company: company.trim(),
        focus: focus.trim() || null,
      };
      const started = await apiPost<ScrapeJobStarted>(
        "/qualification/check",
        body,
      );
      startedAtRef.current = Date.now();
      setNow(Date.now());
      setAsked({ company: body.company, focus: body.focus ?? null });
      setJob(null);
      setAwaitingFirstPoll(true);
      setJobId(started.job_id);
      track(started.job_id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "failed to start qualification check",
      );
    } finally {
      setStarting(false);
    }
  }

  function handleNewCheck() {
    setCompany("");
    setFocus("");
    setAsked(null);
    setFinished(null);
    setJob(null);
    setJobId(null);
    setError(null);
    setNotice(null);
  }

  const steps = quickCheckSteps(asked?.focus ?? null);
  const states = stepStates(steps.length, job?.progress ?? null);
  const startMs = job?.created_at
    ? Date.parse(job.created_at)
    : startedAtRef.current;

  return (
    <div>
      <PageHeader
        title="Quick Check"
        description="Research a company right now: enrich it and judge it against your active criteria. No upload or discovery run needed."
      />

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="check-company">Company name or website</Label>
              <Input
                id="check-company"
                type="text"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="e.g. Acme Inc or acme.com"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="check-focus" className="flex items-center gap-2">
                Focus area (optional)
                <InfoTip label="About the focus area">
                  Type an area to research the company around, for example a
                  technology or a service line. The check then looks for
                  evidence about that area and judges fit for it. Leave it empty
                  to judge the company overall.
                </InfoTip>
              </Label>
              <Input
                id="check-focus"
                type="text"
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                placeholder="e.g. a technology or service line"
                maxLength={200}
              />
            </div>
            <div className="flex items-center gap-3">
              <Button
                type="submit"
                disabled={!canSubmit || starting}
                className="self-start"
              >
                {starting
                  ? "Starting…"
                  : running
                    ? "Checking…"
                    : "Check company"}
              </Button>
              {(finished || asked) && !running && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleNewCheck}
                >
                  New check
                </Button>
              )}
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            {notice && (
              <p className="text-sm text-muted-foreground">{notice}</p>
            )}
          </form>
        </CardContent>
      </Card>

      {running && (
        <Card className="mt-6" aria-live="polite">
          <CardContent>
            <div className="flex flex-wrap items-center gap-3">
              <Loader2
                className="size-5 animate-spin text-primary"
                aria-hidden="true"
              />
              <p className="font-semibold">
                Checking {asked?.company ?? "the company"}
                {asked?.focus ? ` · ${asked.focus}` : ""}
              </p>
              <span className="text-sm tabular-nums text-muted-foreground">
                {elapsedLabel(startMs, now)}
              </span>
            </div>
            <ol className="mt-3 flex flex-col gap-1.5">
              {steps.map((label, index) => (
                <li
                  key={label}
                  className={cn(
                    "flex items-center gap-2 text-sm",
                    states[index] === "waiting"
                      ? "text-muted-foreground"
                      : "text-foreground",
                  )}
                >
                  {states[index] === "done" ? (
                    <Check
                      className="size-4 text-chip-success-fg"
                      aria-hidden="true"
                    />
                  ) : states[index] === "current" ? (
                    <Loader2
                      className="size-4 animate-spin"
                      aria-hidden="true"
                    />
                  ) : (
                    <Circle className="size-4" aria-hidden="true" />
                  )}
                  {label}
                </li>
              ))}
            </ol>
            <p className="mt-3 text-xs text-muted-foreground">
              This usually takes a minute or two. You can leave this page and
              come back; the result will be here.
            </p>
          </CardContent>
        </Card>
      )}

      {!running && job?.status === "failed" && (
        <p className="mt-6 text-sm text-destructive">{job.error}</p>
      )}

      {finished && (
        <div className="mt-6">
          {running && (
            <p className="mb-2 text-xs text-muted-foreground">
              Previous check, shown until the new one finishes.
            </p>
          )}
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <Link
              to={`/companies/${finished.result.company_id}`}
              className="text-lg font-semibold text-primary-text hover:underline"
            >
              {finished.result.company_name}
            </Link>
            {finished.result.company_domain && (
              <WebsiteLink
                domain={finished.result.company_domain}
                className="text-sm"
              />
            )}
            <Badge
              variant={
                finished.result.company_created ? "secondary" : "outline"
              }
            >
              {finished.result.company_created
                ? "New company"
                : "Existing company"}
            </Badge>
            {finished.result.focus && (
              <Badge variant="outline">Focus: {finished.result.focus}</Badge>
            )}
          </div>
          <QualificationResultsTable results={finished.results} />
        </div>
      )}
    </div>
  );
}
