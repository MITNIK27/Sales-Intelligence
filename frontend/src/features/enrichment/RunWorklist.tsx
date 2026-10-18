import { Check, Copy, ExternalLink } from "lucide-react";
import { WebsiteLink } from "@/components/WebsiteLink";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import type {
  Draft,
  MarketDiscoveryWorklist,
  WorklistContact,
  WorklistCriterion,
  WorklistDraft,
  ScoreBreakdown,
  WorklistRow,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

const LIVE_REFRESH_MS = 3000;

// The rep's worklist for one run: companies worth acting on (qualified, with at least one
// primary-target candidate contact), the evidence needed to pick the right person (role, LinkedIn
// profile, email if one was found), and one click per candidate that confirms the person and
// writes their draft. Nothing is drafted for anyone the rep did not choose. Everything else is
// collapsed under one line with a reason each, so nothing is silently dropped.
//
// While the run is still going (`live`), the list refreshes so companies appear as they finish.
export function RunWorklist({
  runId,
  productId,
  live,
}: {
  runId: string;
  productId: string | null;
  live: boolean;
}) {
  const [worklist, setWorklist] = useState<MarketDiscoveryWorklist | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    return apiGet<MarketDiscoveryWorklist>(
      `/market-discovery/${runId}/companies`,
    )
      .then((data) => {
        setWorklist(data);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "failed to load results");
      });
  }, [runId]);

  useEffect(() => {
    load();
    if (!live) return;
    const timer = window.setInterval(load, LIVE_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load, live]);

  if (error && !worklist)
    return <p className="mt-4 text-sm text-destructive">{error}</p>;
  if (!worklist)
    return (
      <p className="mt-4 text-sm text-muted-foreground">Loading results…</p>
    );

  const { ready, not_shown: notShown } = worklist;
  // Mid-run, companies that haven't been qualified yet all look "not shown"; an empty
  // "Ready for you" block would only mislead. The status card above shows real progress.
  if (live && ready.length === 0) return null;
  return (
    <div className="mt-6 flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-bold">
          Ready for you{" "}
          <span className="text-muted-foreground">({ready.length})</span>
          {live && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              updating live…
            </span>
          )}
        </h2>
        <p className="text-sm text-muted-foreground">
          Qualified companies with likely decision-makers. Pick the right person
          and a draft is written for them — nothing is drafted until you choose.
        </p>
      </div>

      {ready.length === 0 && !live && (
        <Card>
          <CardContent>
            <p className="text-sm">
              No company made it through every stage this run
              {notShown.length > 0 ? " — the reasons are listed below." : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {ready.map((row) => (
        <ReadyRow
          key={row.company_id}
          row={row}
          productId={productId}
          onChanged={load}
        />
      ))}

      {notShown.length > 0 && (
        <details className="rounded-md border border-border">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">
            {notShown.length} not shown — why
          </summary>
          <ul className="flex flex-col divide-y divide-border border-t border-border">
            {notShown.map((row) => (
              <li key={row.company_id} className="px-4 py-2 text-sm">
                <Link
                  to={`/companies/${row.company_id}`}
                  className="font-medium hover:underline"
                >
                  {row.name}
                </Link>
                <span className="text-muted-foreground">
                  {" "}
                  — {row.skip_reason}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function ReadyRow({
  row,
  productId,
  onChanged,
}: {
  row: WorklistRow;
  productId: string | null;
  onChanged: () => void;
}) {
  const contactCount = row.candidates.length;
  const draftCount = row.candidates.filter((c) => c.draft).length;

  return (
    <Card>
      <CardContent>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <Link
              to={`/companies/${row.company_id}`}
              className="text-base font-semibold hover:underline"
            >
              {row.name}
            </Link>
            {row.domain && (
              <WebsiteLink domain={row.domain} className="ml-2 text-sm" />
            )}
            <p className="flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
              {row.industry && (
                <FactWithSource
                  label={row.industry}
                  source={row.provenance?.industry?.source}
                />
              )}
              {row.employee_count_range && (
                <FactWithSource
                  label={`${row.employee_count_range} employees`}
                  source={row.provenance?.employee_count_range?.source}
                />
              )}
            </p>
            {row.description && (
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {row.description}
                {row.provenance?.description?.source && (
                  <SourceChip source={row.provenance.description.source} />
                )}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {row.verdict === "could_not_determine" && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-800">
                Needs evidence
              </span>
            )}
            {row.priority_score != null && (
              <span
                className="rounded bg-primary/10 px-1.5 py-0.5 text-xs font-semibold"
                title="Priority Score (0-100): market fit, size, industry, signals, news, technology, contacts"
              >
                Score {Math.round(row.priority_score)}
              </span>
            )}
            <span className="text-xs text-muted-foreground">
              data: {row.data_source}
            </span>
          </div>
        </div>

        {row.why && (
          <p className="mt-2 text-sm">
            <span className="font-semibold">Why it qualified: </span>
            {row.why}
          </p>
        )}

        <CriteriaEvidence criteria={row.criteria} confidence={row.confidence} />
        <ScoreDetails breakdown={row.score_breakdown} />

        <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Contacts · {contactCount} candidate{contactCount === 1 ? "" : "s"} ·{" "}
          {draftCount} draft
          {draftCount === 1 ? "" : "s"}
        </p>
        <div className="mt-1 flex flex-col divide-y divide-border border-t border-border">
          {row.candidates.map((candidate) => (
            <CandidateRow
              key={candidate.contact_id}
              companyId={row.company_id}
              candidate={candidate}
              productId={productId}
              onChanged={onChanged}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function CandidateRow({
  companyId,
  candidate,
  productId,
  onChanged,
}: {
  companyId: string;
  candidate: WorklistContact;
  productId: string | null;
  onChanged: () => void;
}) {
  const [draft, setDraft] = useState<WorklistDraft | null>(candidate.draft);
  const [open, setOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Confirm the person (if still flagged), then write their draft: two existing endpoints, one
  // click. Only this contact gets a draft, so cost follows the rep's choice.
  async function chooseAndDraft() {
    if (!productId) return;
    setWorking(true);
    setError(null);
    try {
      if (candidate.needs_review) {
        await apiPost(`/contacts/${candidate.contact_id}/confirm`);
      }
      const created = await apiPost<Draft>(`/companies/${companyId}/drafts`, {
        contact_id: candidate.contact_id,
        product_id: productId,
        draft_type: "first_touch",
      });
      setDraft({
        draft_id: created.id,
        subject: created.subject,
        body: created.body,
        status: created.status,
      });
      setOpen(true);
      onChanged();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "failed to write the draft",
      );
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="text-sm">
          <p className="font-medium">
            {candidate.full_name ?? "Unnamed"}
            {candidate.role_title ? (
              <span className="font-normal"> — {candidate.role_title}</span>
            ) : null}
          </p>
          <p className="text-muted-foreground">
            {candidate.category ?? "Primary target"}
            {candidate.needs_review
              ? " · found via search, not yet confirmed"
              : ""}
            {candidate.confidence != null
              ? ` · ${Math.round(candidate.confidence * 100)}% sure they work here`
              : ""}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
            {candidate.linkedin_url ? (
              <a
                href={candidate.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-primary-text hover:underline"
              >
                LinkedIn profile <ExternalLink className="size-3" />
              </a>
            ) : (
              <span className="text-muted-foreground">LinkedIn not found</span>
            )}
            {candidate.email ? (
              <span>{candidate.email}</span>
            ) : (
              <span className="text-muted-foreground">Email not found</span>
            )}
          </p>
        </div>

        {draft ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Hide draft" : "Review draft"}
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            onClick={chooseAndDraft}
            disabled={working || !productId}
            title={
              !productId
                ? "Choose a product above before writing a draft"
                : undefined
            }
          >
            {working ? "Writing…" : "This is the right person — write draft"}
          </Button>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
      {draft && open && (
        <DraftEditor
          draft={draft}
          onDiscarded={() => setDraft(null)}
          onError={setError}
        />
      )}
    </div>
  );
}

function DraftEditor({
  draft,
  onDiscarded,
  onError,
}: {
  draft: WorklistDraft;
  onDiscarded: () => void;
  onError: (message: string) => void;
}) {
  const [subject, setSubject] = useState(draft.subject ?? "");
  const [body, setBody] = useState(draft.body);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      await apiPatch<Draft>(`/drafts/${draft.draft_id}`, { subject, body });
      setSaved(true);
    } catch (err) {
      onError(err instanceof Error ? err.message : "failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function discard() {
    try {
      await apiPost<Draft>(`/drafts/${draft.draft_id}/discard`);
      onDiscarded();
    } catch (err) {
      onError(err instanceof Error ? err.message : "failed to discard");
    }
  }

  async function copy() {
    try {
      await window.navigator.clipboard.writeText(
        subject ? `Subject: ${subject}\n\n${body}` : body,
      );
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      onError("couldn't copy — select the text and copy it manually");
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2">
      <input
        type="text"
        value={subject}
        onChange={(e) => setSubject(e.target.value)}
        placeholder="Subject"
        aria-label="Draft subject"
        className="h-9 rounded-md border border-input bg-card px-3 text-sm"
      />
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={8}
        aria-label="Draft body"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save edits"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={copy}>
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button type="button" size="sm" variant="destructive" onClick={discard}>
          Discard
        </Button>
        {saved && <span className="text-sm text-success">Saved</span>}
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<
  WorklistCriterion["status"],
  { mark: string; className: string }
> = {
  PASS: { mark: "✓ PASS", className: "text-green-700" },
  FAIL: { mark: "✗ FAIL", className: "text-destructive" },
  UNKNOWN: { mark: "? UNKNOWN", className: "text-amber-700" },
};

// Each requirement with its verdict and the evidence behind it. UNKNOWN is shown as such — it is
// never silently counted as a pass.
function CriteriaEvidence({
  criteria,
  confidence,
}: {
  criteria: WorklistCriterion[];
  confidence: number | null;
}) {
  if (criteria.length === 0) return null;
  const confidenceLabel =
    confidence != null ? ` · confidence ${Math.round(confidence * 100)}%` : "";
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        Evidence — {criteria.length} checks{confidenceLabel}
      </summary>
      <ul className="mt-2 flex flex-col gap-2">
        {criteria.map((c) => (
          <li key={`${c.scope}-${c.name}`}>
            <span
              className={`font-semibold ${STATUS_STYLE[c.status].className}`}
            >
              {STATUS_STYLE[c.status].mark}
            </span>{" "}
            {c.name}
            {c.hard && (
              <span className="text-xs text-muted-foreground"> (hard)</span>
            )}
            {c.evidence_quote && (
              <p className="ml-4 text-xs text-muted-foreground">
                “{c.evidence_quote}”{c.source && ` — ${c.source}`}
                {c.url && (
                  <>
                    {" "}
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline"
                    >
                      link
                    </a>
                  </>
                )}
                {c.confidence != null &&
                  ` · ${Math.round(c.confidence * 100)}%`}
              </p>
            )}
            {!c.evidence_quote && c.reasoning && (
              <p className="ml-4 text-xs text-muted-foreground">
                {c.reasoning}
              </p>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

const COMPONENT_LABELS: Record<string, string> = {
  market_fit: "Market fit",
  company_size: "Company size",
  industry_relevance: "Industry relevance",
  business_signals: "Business signals",
  recent_news: "Recent news",
  technology_maturity: "Technology maturity",
  contact_availability: "Contact availability",
};

// How the Priority Score was made up, so a rep can see why one company outranks another.
function ScoreDetails({ breakdown }: { breakdown: ScoreBreakdown | null }) {
  if (!breakdown?.components) return null;
  return (
    <details className="mt-1 text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        How the score was made
      </summary>
      <table className="mt-2 w-full text-xs">
        <tbody>
          {Object.entries(breakdown.components).map(([key, c]) => (
            <tr key={key} className="border-t border-border">
              <td className="py-1 pr-2">{COMPONENT_LABELS[key] ?? key}</td>
              <td className="py-1 pr-2 text-muted-foreground">{c.note}</td>
              <td className="py-1 text-right tabular-nums">
                {c.points} / {c.weight}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  "contextdev:brand": "context.dev",
  "contextdev:scrape": "context.dev",
  contextdev: "context.dev",
  "scraper:companysite": "website",
};

function sourceLabel(source: string): string {
  return (
    SOURCE_LABELS[source] ??
    (source.startsWith("contextdev") ? "context.dev" : "website")
  );
}

// Where a fact came from, so a rep can weigh it: a structured vendor record vs. text read off the
// company's own site.
function SourceChip({ source }: { source: string }) {
  return (
    <span className="ml-1 rounded bg-muted px-1 py-0.5 text-[10px] font-medium text-muted-foreground">
      {sourceLabel(source)}
    </span>
  );
}

function FactWithSource({ label, source }: { label: string; source?: string }) {
  return (
    <span>
      {label}
      {source && <SourceChip source={source} />}
    </span>
  );
}
