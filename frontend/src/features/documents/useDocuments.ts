import { useCallback, useEffect, useState } from "react";

import { apiGet } from "@/api/client";
import type {
  DocumentDetailData,
  DocumentPagesData,
  DocumentsStatusInfo,
  LibraryDocument,
} from "@/api/types";
import { isBusy } from "@/features/documents/documentLabels";

const POLL_MS = 2000;
const PAGE_STEP = 50;

// The library: whether documents are switched on, and the list. Polls only while a document is
// waiting or being read, so a finished library costs nothing.
export function useDocuments() {
  const [status, setStatus] = useState<DocumentsStatusInfo | null>(null);
  const [documents, setDocuments] = useState<LibraryDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const info = await apiGet<DocumentsStatusInfo>("/documents/status");
      setStatus(info);
      setDocuments(
        info.enabled ? await apiGet<LibraryDocument[]>("/documents") : [],
      );
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "could not load the documents",
      );
    }
  }, []);

  useEffect(() => {
    // A one-off load on arrival; later updates come from `refresh`, which the page calls.
    void refresh();
  }, [refresh]);

  const anyBusy = (documents ?? []).some((d) => isBusy(d.status));
  useEffect(() => {
    if (!anyBusy) return;
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [anyBusy, refresh]);

  return { status, documents, error, refresh };
}

// One document in full: its versions, what happened while it was read, and what was read from it,
// a page at a time. Polls while it is being read, and loads its pages once it is ready.
export function useDocumentDetail(documentId: string | null) {
  const [detail, setDetail] = useState<DocumentDetailData | null>(null);
  const [pages, setPages] = useState<DocumentPagesData | null>(null);
  const [limit, setLimit] = useState(PAGE_STEP);
  const [error, setError] = useState<string | null>(null);

  const status = detail?.status;
  const load = useCallback(async () => {
    if (!documentId) return;
    try {
      const next = await apiGet<DocumentDetailData>(`/documents/${documentId}`);
      setDetail(next);
      setError(null);
      if (!isBusy(next.status) || next.is_searchable) {
        setPages(
          await apiGet<DocumentPagesData>(
            `/documents/${documentId}/pages?limit=${limit}`,
          ),
        );
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "could not load this document",
      );
    }
  }, [documentId, limit]);

  useEffect(() => {
    // Reset when another document is opened, then load it.
    setDetail(null);
    setPages(null);
    setLimit(PAGE_STEP);
  }, [documentId]);

  useEffect(() => {
    void load();
  }, [load]);

  const busy = status !== undefined && isBusy(status);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [busy, load]);

  const showMore = useCallback(() => setLimit((n) => n + PAGE_STEP), []);
  return { detail, pages, error, reload: load, showMore };
}
