import { FileText, Loader2 } from "lucide-react";
import { useRef, useState, type ComponentRef, type FormEvent } from "react";

import { apiDelete, apiPatch, apiPost, apiUpload } from "@/api/client";
import type {
  DocumentAssetInfo,
  DocumentDetailData,
  DocumentVersionInfo,
} from "@/api/types";
import { FilterButton, type FilterOption } from "@/components/FilterButton";
import { SkeletonLines } from "@/components/Skeleton";
import { Tabs } from "@/components/Tabs";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  EVENT_CLASS,
  STATUS_CLASS,
  STATUS_LABEL,
  TYPE_LABEL,
  assetKindLabel,
  contentSummary,
  duration,
  fileSize,
  isBusy,
  pictureSummary,
  stepLabel,
  writtenBy,
} from "@/features/documents/documentLabels";
import { DocumentText } from "@/features/documents/DocumentText";
import { useDocumentDetail } from "@/features/documents/useDocuments";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

type TabId = "read" | "pictures" | "versions" | "activity";

// One document in a window over the library, so the list behind keeps its place. Shows what the
// app actually read (page by page), which words a model wrote, every version, and what happened
// while it was read. Renaming, tying to offerings, adding a version and deleting live here too.
export function DocumentDetailDialog({
  documentId,
  offeringOptions,
  onClose,
  onChanged,
}: {
  documentId: string | null;
  offeringOptions: FilterOption[];
  onClose: () => void;
  onChanged: () => void;
}) {
  return (
    <Dialog
      open={documentId !== null}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      {documentId && (
        <DocumentDetailContent
          key={documentId}
          documentId={documentId}
          offeringOptions={offeringOptions}
          onClose={onClose}
          onChanged={onChanged}
        />
      )}
    </Dialog>
  );
}

function DocumentDetailContent({
  documentId,
  offeringOptions,
  onClose,
  onChanged,
}: {
  documentId: string;
  offeringOptions: FilterOption[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const { detail, pages, error, reload, showMore } =
    useDocumentDetail(documentId);
  const [tab, setTab] = useState<TabId>("read");
  const [name, setName] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const versionInput = useRef<ComponentRef<"input">>(null);

  async function act(run: () => Promise<unknown>) {
    setActionError(null);
    setWorking(true);
    try {
      await run();
      await reload();
      onChanged();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "That did not work.");
    } finally {
      setWorking(false);
    }
  }

  const hasPictures = (pages?.assets.length ?? 0) > 0;
  const tabs: { id: TabId; label: string }[] = [
    { id: "read", label: "What was read" },
    ...(hasPictures ? [{ id: "pictures" as const, label: "Pictures" }] : []),
    { id: "versions", label: "Versions" },
    { id: "activity", label: "Activity" },
  ];

  return (
    <DialogContent className="overflow-hidden">
      <div className="flex items-start gap-3 border-b border-border p-5 pr-14">
        <div className="grid size-12 shrink-0 place-items-center bg-secondary">
          <FileText className="size-6 text-warning" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <DialogTitle className="truncate">
            {detail?.name ?? "Document"}
          </DialogTitle>
          <DialogDescription>
            {detail
              ? `${TYPE_LABEL[detail.media_type]} · ${fileSize(detail.size_bytes)} · ${detail.original_filename} · added ${timeAgo(detail.created_at)}`
              : "Loading…"}
          </DialogDescription>
        </div>
      </div>

      <div className="overflow-y-auto p-5">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {!detail && !error && <SkeletonLines lines={6} />}
        {detail && (
          <>
            <Summary detail={detail} />

            <form
              className="mt-4 flex flex-wrap items-center gap-3"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                const next = (name ?? detail.name).trim();
                if (next && next !== detail.name)
                  void act(() =>
                    apiPatch(`/documents/${documentId}`, { name: next }),
                  );
              }}
            >
              <Input
                aria-label="Document name"
                value={name ?? detail.name}
                onChange={(e) => setName(e.target.value)}
                className="h-10 w-72 max-w-full"
                maxLength={255}
              />
              <Button
                type="submit"
                variant="action"
                disabled={
                  working || !name || name.trim() === "" || name === detail.name
                }
              >
                Save name
              </Button>
              <FilterButton
                label="About"
                options={offeringOptions}
                selected={detail.offerings.map((o) => o.id)}
                onToggle={(id) => {
                  const ids = detail.offerings.map((o) => o.id);
                  void act(() =>
                    apiPatch(`/documents/${documentId}`, {
                      product_ids: ids.includes(id)
                        ? ids.filter((x) => x !== id)
                        : [...ids, id],
                    }),
                  );
                }}
                onClear={() =>
                  void act(() =>
                    apiPatch(`/documents/${documentId}`, { product_ids: [] }),
                  )
                }
                emptyText="General (any offering)"
                note="Which offerings this document is about. Left general, it can inform any of them."
              />
            </form>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                ref={versionInput}
                type="file"
                className="sr-only"
                aria-label="Choose the new version"
                accept=".pdf,.pptx,.docx,.md,.markdown,.txt"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  const form = new FormData();
                  form.append("file", file);
                  void act(() =>
                    apiUpload(`/documents/${documentId}/versions`, form),
                  );
                }}
              />
              <Button
                type="button"
                variant="action"
                disabled={working}
                onClick={() => versionInput.current?.click()}
              >
                Upload a new version
              </Button>
              {detail.can_reprocess && (
                <Button
                  type="button"
                  variant="action"
                  disabled={working}
                  onClick={() =>
                    void act(() =>
                      apiPost(`/documents/${documentId}/reprocess`),
                    )
                  }
                >
                  Read it again
                </Button>
              )}
              <Button
                type="button"
                variant="destructive"
                disabled={working}
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete "${detail.name}" and everything read from it? This cannot be undone.`,
                    )
                  ) {
                    setActionError(null);
                    setWorking(true);
                    apiDelete(`/documents/${documentId}`)
                      .then(() => {
                        onChanged();
                        onClose();
                      })
                      .catch((err: unknown) => {
                        setWorking(false);
                        setActionError(
                          err instanceof Error
                            ? err.message
                            : "That did not work.",
                        );
                      });
                  }
                }}
              >
                Delete
              </Button>
              {working && (
                <Loader2
                  className="size-4 animate-spin motion-reduce:animate-none"
                  aria-label="Working"
                />
              )}
            </div>
            {actionError && (
              <p className="mt-2 text-sm text-destructive" role="alert">
                {actionError}
              </p>
            )}

            <div className="mt-6">
              <Tabs
                tabs={tabs}
                active={tab}
                onChange={setTab}
                label="Document details"
              />
              {tab === "read" && (
                <ReadTab detail={detail} pages={pages} onShowMore={showMore} />
              )}
              {tab === "pictures" && pages && (
                <PicturesTab assets={pages.assets} />
              )}
              {tab === "versions" && <VersionsTab versions={detail.versions} />}
              {tab === "activity" && <ActivityTab detail={detail} />}
            </div>
          </>
        )}
      </div>
    </DialogContent>
  );
}

function Summary({ detail }: { detail: DocumentDetailData }) {
  const pictures = pictureSummary(detail.assets);
  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span
          className={cn(
            "px-2 py-0.5 text-xs font-semibold",
            STATUS_CLASS[detail.status],
          )}
        >
          {STATUS_LABEL[detail.status]}
        </span>
        <span>{contentSummary(detail)}</span>
        {pictures && <span className="text-muted-foreground">{pictures}</span>}
        <span className="text-muted-foreground">
          Version {detail.version}
          {detail.version_count > 1 && ` of ${detail.version_count}`}
        </span>
      </div>
      {detail.status === "failed" && detail.error && (
        <p className="text-destructive">{detail.error}</p>
      )}
      {detail.status === "failed" && detail.is_searchable && (
        <p className="text-muted-foreground">
          An earlier version is still being used.
        </p>
      )}
      {!detail.is_searchable && !isBusy(detail.status) && (
        <p className="text-muted-foreground">
          Nothing from this document is being used yet.
        </p>
      )}
    </div>
  );
}

function ReadTab({
  detail,
  pages,
  onShowMore,
}: {
  detail: DocumentDetailData;
  pages: ReturnType<typeof useDocumentDetail>["pages"];
  onShowMore: () => void;
}) {
  if (isBusy(detail.status) && !pages)
    return (
      <p className="text-sm text-muted-foreground">
        This document is being read. The result appears here when it is done.
      </p>
    );
  if (!pages || pages.total === 0)
    return (
      <p className="text-sm text-muted-foreground">
        {detail.status === "failed"
          ? "Nothing was read from this document."
          : "No text yet."}
      </p>
    );
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        Version {pages.version}. This is the text the app keeps from the file,
        in reading order. Boxes marked "described by AI" were written by a model
        describing a picture, not by the author.
      </p>
      {pages.pages.map((page) => (
        <section
          key={page.position}
          className="border border-border bg-card p-4"
          aria-label={page.locator}
        >
          <div className="mb-2 flex flex-wrap items-baseline gap-x-3">
            <h3 className="text-sm font-bold">{page.locator}</h3>
            {page.heading_path && page.heading_path !== page.locator && (
              <span className="text-xs text-muted-foreground">
                {page.heading_path}
              </span>
            )}
          </div>
          <DocumentText text={page.text} />
        </section>
      ))}
      {pages.pages.length < pages.total && (
        <div>
          <Button type="button" variant="action" onClick={onShowMore}>
            Show more ({pages.total - pages.pages.length} left)
          </Button>
        </div>
      )}
    </div>
  );
}

function PicturesTab({ assets }: { assets: DocumentAssetInfo[] }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        Pictures, charts, tables and scanned pages that could not be read as
        text. A model described each one; the model and prompt are shown so you
        can tell its words from the document's.
      </p>
      {assets.map((asset) => (
        <section
          key={asset.position}
          className="border border-border bg-card p-4 text-sm"
        >
          <div className="mb-1 flex flex-wrap items-baseline gap-x-3">
            <h3 className="font-bold">
              {assetKindLabel(asset.kind)} · {asset.locator}
            </h3>
            <span
              className={cn(
                "text-xs font-semibold",
                asset.status === "described"
                  ? "text-chip-success-fg"
                  : asset.status === "failed"
                    ? "text-destructive"
                    : "text-muted-foreground",
              )}
            >
              {asset.status === "described"
                ? "Described"
                : asset.status === "failed"
                  ? "Could not be described"
                  : "Not described"}
            </span>
          </div>
          {asset.description && <DocumentText text={asset.description} />}
          {asset.note && <p className="text-muted-foreground">{asset.note}</p>}
          {writtenBy(asset) && (
            <p className="mt-2 text-xs text-muted-foreground">
              {writtenBy(asset)}
              {asset.est_cost_usd !== null &&
                ` · about $${asset.est_cost_usd.toFixed(4)}`}
            </p>
          )}
        </section>
      ))}
    </div>
  );
}

function VersionsTab({ versions }: { versions: DocumentVersionInfo[] }) {
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {versions.map((v) => (
        <li
          key={v.id}
          className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border border-border bg-card p-3"
        >
          <span className="font-bold">Version {v.version}</span>
          <span
            className={cn(
              "px-2 py-0.5 text-xs font-semibold",
              STATUS_CLASS[v.status],
            )}
          >
            {STATUS_LABEL[v.status]}
          </span>
          {v.is_current && (
            <span className="text-xs font-semibold text-primary-text">
              In use
            </span>
          )}
          <span className="text-muted-foreground">
            {v.original_filename} · {fileSize(v.size_bytes)} ·{" "}
            {timeAgo(v.created_at)}
          </span>
          {v.error && (
            <span className="w-full text-destructive">{v.error}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function ActivityTab({ detail }: { detail: DocumentDetailData }) {
  return (
    <ol className="flex flex-col gap-2 text-sm">
      {detail.events.map((event, index) => (
        <li key={`${event.created_at}-${index}`} className="flex gap-3">
          <span className="w-20 shrink-0 text-xs text-muted-foreground">
            {timeAgo(event.created_at)}
          </span>
          <span className="w-20 shrink-0 font-semibold">
            {stepLabel(event.step)}
          </span>
          <span className={EVENT_CLASS[event.status]}>
            {event.message}
            {duration(event.duration_ms) && (
              <span className="text-muted-foreground">
                {" "}
                · {duration(event.duration_ms)}
              </span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}
