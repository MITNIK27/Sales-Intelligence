import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookmarkPlus,
  CircleCheck,
  CircleHelp,
  CircleX,
  Loader2,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";

import { StatusTag } from "@/components/StatusTag";
import { EvidenceQuote } from "@/features/quicklook/EvidenceQuote";
import { WebsiteLink } from "@/components/WebsiteLink";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Call, Snapshot } from "@/features/quicklook/api";
import {
  CALL_TITLE,
  CRITERION_LABEL,
  CRITERION_TONE,
  OFFERING_BAND_LABEL,
  OFFERING_BAND_TONE,
} from "@/features/quicklook/callStyle";
import { formatDateTime } from "@/lib/format";
import { safeHref } from "@/lib/safeHref";
import { cn } from "@/lib/utils";

const CALL_ICON: Record<Call, typeof CircleCheck> = {
  yes: CircleCheck,
  maybe: TriangleAlert,
  no: CircleX,
  unclear: CircleHelp,
};

// Colours for the verdict banner. The icon and the words say the same thing, so colour is never
// the only signal.
const CALL_BANNER: Record<Call, string> = {
  yes: "border-chip-success-fg bg-chip-success-bg text-chip-success-fg",
  maybe: "border-chip-warning-fg bg-chip-warning-bg text-chip-warning-fg",
  no: "border-chip-rejected-fg bg-chip-rejected-bg text-chip-rejected-fg",
  unclear: "border-border bg-muted text-foreground",
};

export type SnapshotActions = {
  working: "save" | "deeper" | "refresh" | null;
  savedCompanyId: string | null;
  onGoDeeper: () => void;
  onSave: () => void;
  onRefresh: () => void;
  onNotThisOne: () => void;
};

export function SnapshotCard({
  snapshot,
  notes,
  actions,
}: {
  snapshot: Snapshot;
  notes: string[];
  actions: SnapshotActions;
}) {
  const Icon = CALL_ICON[snapshot.call];
  const known = actions.savedCompanyId ?? snapshot.existing_company_id;
  const busy = actions.working !== null;

  return (
    <Card className="mt-6">
      <CardContent className="flex flex-col gap-6">
        <div
          className={cn(
            "flex items-start gap-3 rounded-xl border-l-4 p-4",
            CALL_BANNER[snapshot.call],
          )}
        >
          <Icon className="mt-0.5 size-6 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-lg font-bold">{CALL_TITLE[snapshot.call]}</p>
            <p className="text-sm text-foreground">{snapshot.call_reason}</p>
          </div>
        </div>

        <div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 className="text-2xl font-bold">{snapshot.name}</h2>
            <WebsiteLink domain={snapshot.domain} className="text-sm" />
            {snapshot.industry && (
              <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium">
                {snapshot.industry}
              </span>
            )}
            {snapshot.size_hint && (
              <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium">
                {snapshot.size_hint}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {snapshot.focus ? `Researched around: ${snapshot.focus}. ` : ""}
            Showing {snapshot.name} ({snapshot.domain}).{" "}
            <button
              type="button"
              onClick={actions.onNotThisOne}
              disabled={busy}
              className="font-medium text-primary-text underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
            >
              Not this one?
            </button>
          </p>
        </div>

        {snapshot.what_they_do && (
          <section>
            <h3 className="mb-1 text-sm font-bold uppercase tracking-wide text-muted-foreground">
              What they do
            </h3>
            <p className="text-base">{snapshot.what_they_do}</p>
          </section>
        )}

        {snapshot.working_on.length > 0 && (
          <section>
            <h3 className="mb-1 text-sm font-bold uppercase tracking-wide text-muted-foreground">
              What they are working on
            </h3>
            <ul className="flex flex-col gap-3">
              {snapshot.working_on.map((w) => (
                <li key={w.point}>
                  <p className="text-base">{w.point}</p>
                  <EvidenceQuote
                    quote={w.quote}
                    kind={w.source_kind}
                    date={w.source_date}
                    url={w.source_url}
                  />
                </li>
              ))}
            </ul>
          </section>
        )}

        {(snapshot.relevance || snapshot.offerings.length > 0) && (
          <section>
            <h3 className="mb-1 text-sm font-bold uppercase tracking-wide text-muted-foreground">
              What we could offer
            </h3>
            {snapshot.relevance && (
              <p className="mb-3 text-base">{snapshot.relevance}</p>
            )}
            {snapshot.offerings.length > 0 && (
              <ul className="flex flex-col gap-3">
                {snapshot.offerings.map((o) => {
                  return (
                    <li
                      key={o.product_id}
                      className="rounded-xl border border-border p-3"
                    >
                      <div className="flex flex-wrap items-center gap-x-3">
                        <span className="font-semibold">{o.name}</span>
                        <StatusTag tone={OFFERING_BAND_TONE[o.band]}>
                          {OFFERING_BAND_LABEL[o.band]}
                        </StatusTag>
                      </div>
                      {o.idea && <p className="mt-1 text-base">{o.idea}</p>}
                      {o.why_now && (
                        <p className="text-sm text-muted-foreground">
                          Why now: {o.why_now}
                        </p>
                      )}
                      <p className="mt-1 text-sm text-muted-foreground">
                        {o.reason}
                      </p>
                      {o.quote && (
                        <EvidenceQuote
                          quote={o.quote}
                          kind={o.source_kind}
                          date={o.source_date}
                          url={o.source_url}
                        />
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        )}

        {snapshot.criteria.length > 0 && (
          <section>
            <h3 className="mb-1 text-sm font-bold uppercase tracking-wide text-muted-foreground">
              Your criteria
            </h3>
            <ul className="flex flex-col gap-3">
              {snapshot.criteria.map((c) => {
                const href = safeHref(c.source_url);
                return (
                  <li
                    key={c.name}
                    className="rounded-xl border border-border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-x-3">
                      <span className="font-semibold">{c.name}</span>
                      <StatusTag tone={CRITERION_TONE[c.verdict]}>
                        {CRITERION_LABEL[c.verdict]}
                      </StatusTag>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {c.reason}
                    </p>
                    {c.quote && (
                      <p className="mt-1 break-words border-l-2 border-border pl-3 text-sm italic">
                        “{c.quote}”
                        {href && (
                          <>
                            {" "}
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="not-italic text-primary-text hover:underline"
                            >
                              Source
                            </a>
                          </>
                        )}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">
              These are for information. They do not change the call above.
            </p>
          </section>
        )}

        {notes.length > 0 && (
          <ul
            role="status"
            className="flex flex-col gap-1 border-l-2 border-border pl-3 text-sm text-muted-foreground"
          >
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
          {known ? (
            <Button asChild>
              <Link to={`/companies/${known}`}>
                {actions.savedCompanyId
                  ? "Open saved company"
                  : "Open company page"}
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          ) : (
            <Button disabled={busy} onClick={actions.onGoDeeper}>
              {actions.working === "deeper" ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <ArrowRight aria-hidden="true" />
              )}
              Go deeper
            </Button>
          )}
          {!known && (
            <Button variant="outline" disabled={busy} onClick={actions.onSave}>
              {actions.working === "save" ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <BookmarkPlus aria-hidden="true" />
              )}
              Save to my companies
            </Button>
          )}
          <Button
            variant="ghost"
            disabled={busy}
            onClick={actions.onRefresh}
            className="ml-auto"
          >
            <RefreshCw
              className={actions.working === "refresh" ? "animate-spin" : ""}
              aria-hidden="true"
            />
            Refresh
          </Button>
        </div>
        <p className="-mt-3 text-xs text-muted-foreground">
          {snapshot.cached ? "Saved answer from " : "Checked "}
          {formatDateTime(snapshot.updated_at)}. Go deeper adds the company to
          your list and starts full research on its page.
        </p>
      </CardContent>
    </Card>
  );
}
