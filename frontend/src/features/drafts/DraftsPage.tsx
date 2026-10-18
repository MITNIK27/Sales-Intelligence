import { Check, ChevronDown, ChevronUp, Copy, ExternalLink, FileText, Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import type { DashboardDraftItem, DashboardDraftList, Draft } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { TablePagination } from "@/components/TablePagination";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

type Tab = "draft" | "sent" | "discarded" | "all";

const TABS: { key: Tab; label: string; hint: string }[] = [
  { key: "draft", label: "To review", hint: "Written, not sent yet" },
  { key: "sent", label: "Sent", hint: "You marked these as sent" },
  { key: "discarded", label: "Discarded", hint: "Removed from your list" },
  { key: "all", label: "All", hint: "Everything" },
];

function parseTab(value: string | null): Tab {
  return value === "sent" || value === "discarded" || value === "all" ? value : "draft";
}

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const STATUS_CHIP: Record<string, { label: string; cls: string }> = {
  draft: { label: "To review", cls: "bg-chip-warning-bg text-chip-warning-fg" },
  sent: { label: "Sent", cls: "bg-chip-success-bg text-chip-success-fg" },
  discarded: { label: "Discarded", cls: "bg-chip-rejected-bg text-chip-rejected-fg" },
};

// Every draft the system has written, in one place: read it, fix it, copy it, mark it sent, or
// discard it. Nothing is deleted outright - "discard" just moves a draft to the Discarded tab.
export function DraftsPage() {
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("status"));
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [list, setList] = useState<DashboardDraftList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    apiGet<DashboardDraftList>(
      `/drafts?status=${tab}&limit=${pageSize}&offset=${(page - 1) * pageSize}`,
    )
      .then(setList)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load drafts"));
  }, [tab, page, pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  function chooseTab(next: Tab) {
    setPage(1);
    setParams(next === "draft" ? {} : { status: next });
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Drafts"
        description="Every message the system has written for you. Review it, edit it, then copy it out and mark it sent — or discard it."
      />

      <div role="tablist" aria-label="Draft status" className="flex flex-wrap gap-2">
        {TABS.map((t) => {
          const count =
            t.key === "all"
              ? list
                ? list.counts.draft + list.counts.sent + list.counts.discarded
                : null
              : (list?.counts[t.key] ?? null);
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => chooseTab(t.key)}
              title={t.hint}
              className={cn(
                "flex items-center gap-2 border px-4 py-2 text-sm transition-colors duration-200",
                active
                  ? "border-primary bg-primary/10 font-semibold"
                  : "border-border bg-card hover:border-primary",
              )}
            >
              {t.label}
              {count !== null && <span className="tabular-nums text-muted-foreground">{count}</span>}
            </button>
          );
        })}
      </div>

      {error && !list ? (
        <ErrorState message={error} onRetry={load} />
      ) : list === null ? (
        <SkeletonLines lines={6} />
      ) : list.items.length === 0 ? (
        <Card>
          <EmptyState
            icon={FileText}
            title={tab === "draft" ? "Nothing waiting for review" : "No drafts here"}
            description={
              tab === "draft"
                ? "Drafts appear here once you pick a person in a search's results and ask for one."
                : "Drafts you move here will show up in this tab."
            }
            action={
              <Button asChild variant="outline">
                <Link to="/">Back to the dashboard</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <>
          <ul className="flex flex-col gap-4">
            {list.items.map((draft) => (
              <DraftCard key={draft.id} draft={draft} onChanged={load} />
            ))}
          </ul>
          <TablePagination
            total={list.total}
            page={page}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(1);
            }}
          />
        </>
      )}
    </div>
  );
}

function DraftCard({ draft, onChanged }: { draft: DashboardDraftItem; onChanged: () => void }) {
  const { showToast } = useToast();
  const [open, setOpen] = useState(false);
  const [subject, setSubject] = useState(draft.subject ?? "");
  const [body, setBody] = useState(draft.body);
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const chip = STATUS_CHIP[draft.status] ?? STATUS_CHIP.draft;
  const editable = draft.status === "draft";
  const dirty = subject !== (draft.subject ?? "") || body !== draft.body;

  async function run(label: string, action: () => Promise<unknown>, success: string) {
    setBusy(label);
    try {
      await action();
      showToast({ description: success, variant: "success" });
      onChanged();
    } catch (err) {
      showToast({
        description: err instanceof Error ? err.message : `failed to ${label}`,
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  const save = () =>
    run("save", () => apiPatch<Draft>(`/drafts/${draft.id}`, { subject, body }), "Draft saved");
  const discard = () =>
    run("discard", () => apiPost<Draft>(`/drafts/${draft.id}/discard`), "Draft discarded");
  const markSent = () =>
    run(
      "mark as sent",
      () =>
        apiPost(`/contacts/${draft.contact_id}/outreach-activities`, {
          channel: draft.channel,
          activity_type: "sent",
          draft_id: draft.id,
        }),
      "Marked as sent",
    );

  async function copy() {
    try {
      await window.navigator.clipboard.writeText(subject ? `Subject: ${subject}\n\n${body}` : body);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      showToast({ description: "Could not copy - select the text and copy it by hand", variant: "error" });
    }
  }

  return (
    <li>
      <Card className={cn(draft.status === "discarded" && "opacity-70")}>
        <CardContent>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-muted-foreground">
                To <span className="font-medium text-foreground">{draft.contact_name ?? "a contact"}</span>
                {draft.contact_role ? `, ${draft.contact_role}` : ""} at{" "}
                <Link
                  to={`/companies/${draft.company_id}`}
                  className="inline-flex items-center gap-1 font-medium text-primary-text hover:underline"
                >
                  {draft.company_name} <ExternalLink className="size-3" />
                </Link>
              </p>
              <p className="mt-1 text-base font-semibold">{draft.subject || "(no subject)"}</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className={cn("px-2 py-0.5 font-medium", chip.cls)}>{chip.label}</span>
              <span>{when(draft.created_at)}</span>
            </div>
          </div>

          {!open && (
            <p className="mt-2 line-clamp-3 whitespace-pre-line text-sm text-muted-foreground">
              {draft.body}
            </p>
          )}

          {open && (
            <div className="mt-3 flex flex-col gap-2">
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                readOnly={!editable}
                aria-label="Draft subject"
                className="h-9 border border-input bg-card px-3 text-sm"
              />
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                readOnly={!editable}
                rows={9}
                aria-label="Draft body"
              />
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setOpen(!open)}>
              {open ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
              {open ? "Collapse" : editable ? "Review & edit" : "Read"}
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={copy}>
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              {copied ? "Copied" : "Copy"}
            </Button>
            {editable && (
              <>
                {open && (
                  <Button type="button" size="sm" onClick={save} disabled={!dirty || busy !== null}>
                    {busy === "save" ? "Saving…" : "Save edits"}
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={markSent}
                  disabled={busy !== null || dirty}
                  title={dirty ? "Save your edits first" : "Log that you sent this message"}
                >
                  <Send className="size-4" />
                  {busy === "mark as sent" ? "Marking…" : "Mark as sent"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  onClick={discard}
                  disabled={busy !== null}
                >
                  Discard
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </li>
  );
}
