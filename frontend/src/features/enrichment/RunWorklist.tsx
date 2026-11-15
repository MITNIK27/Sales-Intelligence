import {
  AlertTriangle,
  Check,
  ChevronRight,
  Copy,
  ExternalLink,
} from "lucide-react";
import { WebsiteLink } from "@/components/WebsiteLink";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import { NotAFitButton } from "@/features/companies/notAFit/NotAFitButton";
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
import { CompanyLogo } from "@/components/CompanyLogo";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
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
  onSummary,
}: {
  runId: string;
  productId: string | null;
  live: boolean;
  // Told how many companies are ready and how many were left out, for the run's summary.
  onSummary?: (ready: number, notShown: number) => void;
}) {
  const [worklist, setWorklist] = useState<MarketDiscoveryWorklist | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  // The company whose details are open in a window over the list.
  const [openId, setOpenId] = useState<string | null>(null);
  const summaryRef = useRef(onSummary);
  summaryRef.current = onSummary;

  const load = useCallback(() => {
    return apiGet<MarketDiscoveryWorklist>(
      `/market-discovery/${runId}/companies`,
    )
      .then((data) => {
        setWorklist(data);
        setError(null);
        summaryRef.current?.(data.ready.length, data.not_shown.length);
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
  // Looked up each time, so the window keeps following the live list and closes if the company
  // leaves it (for example when it is marked not a fit).
  const openRow = ready.find((row) => row.company_id === openId) ?? null;
  // Mid-run, companies that haven't been qualified yet all look "not shown"; an empty
  // "Ready for you" block would only mislead. The status card above shows real progress.
  if (live && ready.length === 0) return null;
  return (
    <div id="run-worklist" className="mt-6 flex scroll-mt-4 flex-col gap-4">
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
          Click a company to see its people and write a draft. Nothing is
          drafted until you choose.
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

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {ready.map((row) => (
          <ReadyCard
            key={row.company_id}
            row={row}
            onOpen={() => setOpenId(row.company_id)}
            onChanged={load}
          />
        ))}
      </div>

      <Dialog
        open={openRow !== null}
        onOpenChange={(next) => {
          if (!next) setOpenId(null);
        }}
      >
        {openRow && (
          <DialogContent className="overflow-hidden">
            <div className="flex items-start gap-3 border-b border-border p-5 pr-14">
              <CompanyLogo name={openRow.name} domain={openRow.domain} />
              <div className="min-w-0">
                <DialogTitle>{openRow.name}</DialogTitle>
                <DialogDescription>
                  {[
                    openRow.industry,
                    openRow.employee_count_range &&
                      `${openRow.employee_count_range} employees`,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "Company details"}
                </DialogDescription>
              </div>
            </div>
            <div className="overflow-y-auto p-5">
              <ReadyDetail
                row={openRow}
                runId={runId}
                productId={productId}
                onChanged={load}
              />
            </div>
          </DialogContent>
        )}
      </Dialog>

      {notShown.length > 0 && (
        <section
          aria-label="Companies not shown"
          className="border border-chip-warning-fg/40 border-l-4 border-l-chip-warning-fg bg-chip-warning-bg"
        >
          <div className="flex items-start gap-3 px-4 py-3">
            <AlertTriangle
              className="mt-0.5 size-5 shrink-0 text-chip-warning-fg"
              aria-hidden="true"
            />
            <div>
              <h3 className="text-base font-bold text-chip-warning-fg">
                {notShown.length}{" "}
                {notShown.length === 1 ? "company was" : "companies were"} not
                shown
              </h3>
              <p className="text-sm text-chip-warning-fg">
                Each one is listed with the reason, so nothing is dropped
                silently.
              </p>
            </div>
          </div>
          <ul className="flex flex-col divide-y divide-chip-warning-fg/20 border-t border-chip-warning-fg/20 bg-card">
            {notShown.map((row) => (
              <li
                key={row.company_id}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm"
              >
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <CompanyLogo
                    name={row.name}
                    domain={row.domain}
                    className="size-10 text-base"
                  />
                  <div className="min-w-0">
                    <Link
                      to={`/companies/${row.company_id}?run=${runId}`}
                      className="font-semibold text-primary-text hover:underline"
                    >
                      {row.name}
                    </Link>
                    <p className="text-muted-foreground">{row.skip_reason}</p>
                  </div>
                </div>
                <NotAFitButton companyIds={[row.company_id]} onDone={load} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// The first sentence of the reason a company qualified: the one line that says why it is here.
export function firstSentence(text: string | null): string | null {
  if (!text) return null;
  const match = text.match(/^.*?[.!?](?=\s|$)/);
  return (match ? match[0] : text).trim();
}

// A company as a short card: logo, who it is, why it fits, how many people to look at. The whole
// card is clickable and says so (it changes colour under the pointer and ends in "View details");
// the details open in a window so the list behind keeps its place. The rest (the whole brief,
// areas, history) is on the company page.
function ReadyCard({
  row,
  onOpen,
  onChanged,
}: {
  row: WorklistRow;
  onOpen: () => void;
  onChanged: () => void;
}) {
  const people = row.candidates.length;
  const drafts = row.candidates.filter((c) => c.draft).length;
  const why = firstSentence(row.why);
  return (
    <Card
      onClick={onOpen}
      className="group cursor-pointer transition-colors hover:border-primary hover:bg-muted motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 motion-reduce:transition-none"
    >
      <CardContent>
        <div className="flex items-start gap-3">
          <CompanyLogo name={row.name} domain={row.domain} />
          <button
            type="button"
            aria-haspopup="dialog"
            aria-label={`View details for ${row.name}`}
            onClick={(e) => {
              e.stopPropagation();
              onOpen();
            }}
            className="min-w-0 flex-1 cursor-pointer text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-base font-semibold group-hover:text-primary-text">
                {row.name}
              </span>
              {row.verdict === "could_not_determine" ? (
                <span className="bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-800">
                  Needs evidence
                </span>
              ) : (
                <span className="bg-chip-success-bg px-1.5 py-0.5 text-xs font-semibold text-chip-success-fg">
                  Qualified
                </span>
              )}
              {row.priority_score != null && (
                <span
                  className="bg-primary/10 px-1.5 py-0.5 text-xs font-semibold"
                  title="Priority Score (0-100)"
                >
                  Score {Math.round(row.priority_score)}
                </span>
              )}
            </span>
            <span className="mt-0.5 block text-sm text-muted-foreground">
              {[
                row.industry,
                row.employee_count_range &&
                  `${row.employee_count_range} employees`,
                row.domain,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
            {why && <span className="mt-1 line-clamp-2 text-sm">{why}</span>}
            <span className="mt-3 flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
              <span>
                {people} {people === 1 ? "person" : "people"} to review
                {drafts > 0 && ` · ${drafts} draft${drafts === 1 ? "" : "s"}`}
              </span>
              <span className="inline-flex items-center gap-0.5 font-semibold text-primary-text">
                View details
                <ChevronRight
                  className="size-4 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
                  aria-hidden="true"
                />
              </span>
            </span>
          </button>
          {/* Its own click must not open the card. */}
          <div onClick={(e) => e.stopPropagation()} className="shrink-0">
            <NotAFitButton companyIds={[row.company_id]} onDone={onChanged} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// What was shown on the long card before: why it qualified, the evidence, how the score was made
// and each candidate with the draft button.
function ReadyDetail({
  row,
  runId,
  productId,
  onChanged,
}: {
  row: WorklistRow;
  runId: string;
  productId: string | null;
  onChanged: () => void;
}) {
  const contactCount = row.candidates.length;
  const draftCount = row.candidates.filter((c) => c.draft).length;

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          {row.description && (
            <p className="line-clamp-3 text-xs text-muted-foreground">
              {row.description}
              {row.provenance?.description?.source && (
                <SourceChip source={row.provenance.description.source} />
              )}
            </p>
          )}
          <p className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
            {row.domain && (
              <WebsiteLink domain={row.domain} className="text-sm" />
            )}
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
            <span className="text-xs">data: {row.data_source}</span>
          </p>
        </div>
        <Link
          to={`/companies/${row.company_id}?run=${runId}`}
          className="text-sm font-medium text-primary-text hover:underline"
        >
          Open company page →
        </Link>
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
    </div>
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
                ? "Choose an offering above before writing a draft"
                : "Confirms this person and writes a first email"
            }
          >
            {working ? "Writing…" : "Write draft"}
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
