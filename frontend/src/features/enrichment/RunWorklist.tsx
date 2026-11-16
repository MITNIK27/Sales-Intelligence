import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronRight,
  Copy,
  ExternalLink,
} from "lucide-react";
import type { ReactNode } from "react";
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
import { StatusTag } from "@/components/StatusTag";
import { ContactTrust } from "@/features/contacts/ContactTrust";
import { Button, buttonVariants } from "@/components/ui/button";
import { CompanyLogo } from "@/components/CompanyLogo";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { countWords, plural } from "@/lib/format";

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
            <div className="flex flex-wrap items-start gap-x-3 gap-y-3 border-b border-border p-5 pr-14">
              <CompanyLogo name={openRow.name} domain={openRow.domain} />
              <div className="min-w-0 flex-1">
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
              <div className="flex flex-wrap items-center gap-2">
                {openRow.domain && (
                  <a
                    href={`https://${openRow.domain}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={buttonVariants({
                      variant: "outline",
                      size: "sm",
                    })}
                  >
                    {openRow.domain}
                    <ExternalLink className="size-3.5" aria-hidden="true" />
                  </a>
                )}
                <Link
                  to={`/companies/${openRow.company_id}?run=${runId}`}
                  className={buttonVariants({ size: "sm" })}
                >
                  Open company page
                  <ArrowRight className="size-3.5" aria-hidden="true" />
                </Link>
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

// What a company's window shows, in the order a rep reads it: what the company is, how it matched
// the search, how it scored, then the people to contact. Each part is its own block with a heading.
function ReadyDetail({
  row,
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
    <div className="flex flex-col gap-6">
      {row.description && (
        <Block title="About the company">
          <p className="text-sm leading-relaxed">{row.description}</p>
        </Block>
      )}

      <Block
        title="How it matched your search"
        aside={
          row.confidence != null
            ? `Confidence ${Math.round(row.confidence * 100)}%`
            : undefined
        }
      >
        {row.criteria.length > 0 ? (
          <ul className="flex flex-col divide-y divide-border border border-border">
            {row.criteria.map((c) => (
              <CriterionRow key={`${c.scope}-${c.name}`} criterion={c} />
            ))}
          </ul>
        ) : row.why ? (
          <p className="text-sm leading-relaxed">{row.why}</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            No checks were set for this search.
          </p>
        )}
      </Block>

      <ScoreDetails
        breakdown={row.score_breakdown}
        score={row.priority_score}
      />

      <Block
        title="People to contact"
        aside={`${contactCount} found · ${draftCount} draft${draftCount === 1 ? "" : "s"}`}
      >
        {!productId && (
          <p className="text-xs text-muted-foreground">
            Choose an offering at the top of this page to write drafts.
          </p>
        )}
        <div className="flex flex-col gap-3">
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
      </Block>
    </div>
  );
}

// One titled block of the window, with an optional note on the right of its heading.
function Block({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-l-4 border-primary pl-3">
        <h3 className="text-base font-bold leading-tight">{title}</h3>
        {aside && (
          <span className="text-sm text-muted-foreground">{aside}</span>
        )}
      </div>
      {children}
    </section>
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
    <div className="border border-border bg-card p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="break-words text-sm font-semibold">
            {candidate.full_name ?? "Unnamed"}
          </p>
          {candidate.role_title && (
            <p className="break-words text-xs">{candidate.role_title}</p>
          )}
          <p className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-0.5">
            {candidate.category && (
              <span className="text-xs text-muted-foreground">
                {candidate.category}
              </span>
            )}
            <ContactTrust
              needsReview={candidate.needs_review}
              confidence={candidate.confidence}
            />
          </p>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-5 gap-y-0.5 text-xs">
            {candidate.linkedin_url ? (
              <a
                href={candidate.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-medium text-primary-text hover:underline"
              >
                LinkedIn profile <ExternalLink className="size-3.5" />
              </a>
            ) : (
              <span className="text-muted-foreground">No LinkedIn found</span>
            )}
            {candidate.email ? (
              <span>{candidate.email}</span>
            ) : (
              <span className="text-muted-foreground">No email found</span>
            )}
          </p>
        </div>

        {draft ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Hide draft" : "Review draft"}
          </Button>
        ) : productId ? (
          <Button
            type="button"
            onClick={chooseAndDraft}
            disabled={working}
            title="Confirms this person and writes a first email"
          >
            {working ? "Writing…" : "Write draft"}
          </Button>
        ) : null}
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
      <p className="text-xs text-muted-foreground">
        {countWords(body)} {plural(countWords(body), "word")}
      </p>
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

const CRITERION_STATUS: Record<
  WorklistCriterion["status"],
  { label: string; tone: "good" | "bad" | "watch" }
> = {
  PASS: { label: "Met", tone: "good" },
  FAIL: { label: "Not met", tone: "bad" },
  UNKNOWN: { label: "Could not confirm", tone: "watch" },
};

// One check with its answer and the evidence behind it. "Could not confirm" is shown as such: it is
// never silently counted as met.
function CriterionRow({ criterion: c }: { criterion: WorklistCriterion }) {
  const status = CRITERION_STATUS[c.status];
  const note = c.evidence_quote ? `“${c.evidence_quote}”` : c.reasoning;
  return (
    <li className="flex flex-col gap-0.5 px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{c.name}</span>
          {c.hard && (
            <span
              role="img"
              aria-label="Must have in the search"
              title="Must have in the search"
              className="size-2.5 shrink-0 cursor-help rounded-full bg-muted-foreground"
            />
          )}
        </span>
        <StatusTag tone={status.tone} className="text-xs">
          {status.label}
        </StatusTag>
      </div>
      {note && (
        <p className="break-words text-xs text-muted-foreground">
          {note}
          {c.evidence_quote && c.source && ` (${c.source})`}
          {c.url && (
            <>
              {" "}
              <a
                href={c.url}
                target="_blank"
                rel="noreferrer"
                className="text-primary-text underline"
              >
                Source
              </a>
            </>
          )}
        </p>
      )}
    </li>
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

// "1 hard requirement(s)" reads as "1 hard requirement": the plural is decided by the number, and
// the first letter is a capital.
export function tidyNote(note: string): string {
  const count = Number(note.match(/^\s*(\d+(?:\.\d+)?)\b/)?.[1]);
  const plural = Number.isFinite(count) && count === 1 ? "" : "s";
  const text = note.replace(/\(s\)/g, plural).trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// How the Priority Score was made up, so a rep can see why one company outranks another: each part
// as a small tile with its points, no bars to read.
function ScoreDetails({
  breakdown,
  score,
}: {
  breakdown: ScoreBreakdown | null;
  score: number | null;
}) {
  if (!breakdown?.components) return null;
  return (
    <Block
      title="Priority score"
      aside={score != null ? `${Math.round(score)} out of 100` : undefined}
    >
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {Object.entries(breakdown.components).map(([key, c]) => (
          <li key={key} className="border border-border px-3 py-2">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm font-semibold">
                {COMPONENT_LABELS[key] ?? key}
              </span>
              <span className="text-sm tabular-nums">
                <span className="font-bold">{c.points}</span>
                <span className="text-muted-foreground"> / {c.weight}</span>
              </span>
            </div>
            {c.note && (
              <p className="text-xs text-muted-foreground">
                {tidyNote(c.note)}
              </p>
            )}
          </li>
        ))}
      </ul>
    </Block>
  );
}
