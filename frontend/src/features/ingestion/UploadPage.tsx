import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, uploadCsv } from "@/api/client";
import type { CsvIngestionStarted, JobStatus } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/Skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { usePersistentState } from "@/lib/usePersistentState";

const POLL_INTERVAL_MS = 1500;

export function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  // The last upload's job id is remembered, so leaving this page and coming back still shows
  // that upload's result (the job itself is re-fetched, never cached).
  const [jobId, setJobId] = usePersistentState<string | null>("upload.jobId", null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pollRef = useRef<number | null>(null);

  function startPolling(pollJobId: string) {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const status = await apiGet<JobStatus>(`/jobs/${pollJobId}`);
        setJob(status);
        if (status.status === "done" || status.status === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
        }
      } catch {
        // One failed poll must not end the loop — the next tick retries.
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => {
    let cancelled = false;
    if (jobId) {
      apiGet<JobStatus>(`/jobs/${jobId}`)
        .then((status) => {
          if (cancelled) return;
          setJob(status);
          if (status.status !== "done" && status.status !== "failed") startPolling(jobId);
        })
        .catch(() => {
          // The remembered job no longer exists (e.g. the database was wiped): forget it.
          if (!cancelled) setJobId(null);
        });
    }
    return () => {
      cancelled = true;
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
    // Runs once on mount, deliberately: it only restores what was remembered.
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setJob(null);
    setSubmitting(true);
    try {
      const started = await uploadCsv<CsvIngestionStarted>("/ingestion/csv", file);
      setJobId(started.job_id);
      startPolling(started.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Upload Prospect CSV"
        description="Bring in a list of companies/contacts and let it dedupe."
      />

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-3">
            <Input
              type="file"
              accept=".csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="h-10 w-auto"
            />
            <Button type="submit" disabled={!file || submitting}>
              {submitting ? "Uploading…" : "Upload"}
            </Button>
          </form>

          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

          {jobId && !job && (
            <div className="mt-4">
              <Skeleton className="h-4 w-72" />
            </div>
          )}
        </CardContent>
      </Card>

      {job && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg font-bold">Upload status: {job.status}</CardTitle>
          </CardHeader>
          <CardContent>
            {job.status === "running" && job.progress && (
              <p className="text-sm text-muted-foreground">
                Processed {job.progress.done} of {job.progress.total} rows…
              </p>
            )}
            {job.status === "failed" && <p className="text-sm text-destructive">{job.error}</p>}
            {job.result && (
              <ul className="mt-2 list-inside list-disc text-sm">
                <li>Companies created: {job.result.companies_created}</li>
                <li>Companies updated: {job.result.companies_updated}</li>
                <li>Contacts created: {job.result.contacts_created}</li>
                <li>Rows skipped: {job.result.rows_skipped}</li>
              </ul>
            )}
            {job.result && job.result.errors.length > 0 && (
              <>
                <h3 className="mt-4 text-sm font-bold">Row errors</h3>
                <ul className="mt-1 list-inside list-disc text-sm text-muted-foreground">
                  {job.result.errors.map((e) => (
                    <li key={e.row_number}>
                      Row {e.row_number}: {e.error}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {job.status === "done" && (
              <Link to="/companies" className="mt-4 inline-block text-primary-text hover:underline">
                View companies →
              </Link>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
