import type {
  DocumentAssetInfo,
  DocumentEvent,
  DocumentMediaType,
  DocumentStatus,
  KnowledgeCardInfo,
  KnowledgeCardKind,
  LibraryDocument,
} from "@/api/types";
import { formatNumber, plural } from "@/lib/format";

export const STATUS_LABEL: Record<DocumentStatus, string> = {
  queued: "Waiting",
  processing: "Reading…",
  ready: "Ready",
  failed: "Failed",
};

export const STATUS_CLASS: Record<DocumentStatus, string> = {
  queued: "bg-muted text-muted-foreground",
  processing: "bg-chip-warning-bg text-chip-warning-fg",
  ready: "bg-chip-success-bg text-chip-success-fg",
  failed: "bg-chip-rejected-bg text-chip-rejected-fg",
};

export const TYPE_LABEL: Record<DocumentMediaType, string> = {
  pdf: "PDF",
  pptx: "Deck",
  docx: "Word",
  md: "Markdown",
  txt: "Text",
};

// What each kind of file is split into, as people say it.
const UNIT: Record<DocumentMediaType, [string, string]> = {
  pdf: ["page", "pages"],
  pptx: ["slide", "slides"],
  docx: ["section", "sections"],
  md: ["section", "sections"],
  txt: ["section", "sections"],
};

export function isBusy(status: DocumentStatus): boolean {
  return status === "queued" || status === "processing";
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// "12 slides · 34 passages", or what is happening instead while there is nothing to count yet.
export function contentSummary(doc: LibraryDocument): string {
  if (isBusy(doc.status)) return "Being read";
  if (doc.status === "failed" && !doc.is_searchable) return "Nothing read";
  const [one, many] = UNIT[doc.media_type];
  const pages = doc.page_count ?? 0;
  return `${formatNumber(pages)} ${plural(pages, one, many)} · ${formatNumber(doc.chunk_count)} ${plural(doc.chunk_count, "passage")}`;
}

// "Indexing for meaning search: 12 of 54", or null when nothing is to be said (done, off, or the
// document is not readable yet).
export function indexingSummary(
  doc: LibraryDocument,
  meaningSearch: boolean,
): string | null {
  if (!meaningSearch || !doc.is_searchable || doc.chunk_count === 0)
    return null;
  if (doc.indexed_chunks >= doc.chunk_count) return null;
  return `Meaning search: ${formatNumber(doc.indexed_chunks)} of ${formatNumber(doc.chunk_count)} indexed`;
}

// How a passage was found, in words a person can use to judge it.
export function matchLabel(hit: {
  similarity: number | null;
  word_match: boolean;
}): string {
  const parts: string[] = [];
  if (hit.similarity !== null)
    parts.push(`meaning ${Math.round(hit.similarity * 100)}%`);
  if (hit.word_match) parts.push("words");
  return parts.length > 0 ? `Matched by ${parts.join(" and ")}` : "Matched";
}

// What happened to the pictures, or null when there were none to describe.
export function pictureSummary(
  assets: LibraryDocument["assets"],
): string | null {
  const parts: string[] = [];
  if (assets.described > 0)
    parts.push(
      `${assets.described} ${plural(assets.described, "picture")} described`,
    );
  if (assets.failed > 0) parts.push(`${assets.failed} could not be described`);
  if (assets.skipped > 0) parts.push(`${assets.skipped} not described`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

const ASSET_KIND: Record<DocumentAssetInfo["kind"], string> = {
  image: "Picture",
  table: "Table",
  scanned_page: "Scanned page",
};

export function assetKindLabel(kind: DocumentAssetInfo["kind"]): string {
  return ASSET_KIND[kind];
}

// "Written by gemini-flash-lite-latest (prompt v1)": always shown next to a description, so nobody
// mistakes a model's words for the document's.
export function writtenBy(asset: DocumentAssetInfo): string | null {
  if (!asset.model_used) return null;
  return `Written by ${asset.model_used}${asset.prompt_version ? ` (prompt ${asset.prompt_version})` : ""}`;
}

const STEP_LABEL: Record<string, string> = {
  upload: "Upload",
  read: "Reading",
  describe: "Pictures",
  chunk: "Passages",
  embed: "Indexing",
  done: "Finished",
  summarise: "Summary",
  failed: "Failed",
};

export function stepLabel(step: string): string {
  return STEP_LABEL[step] ?? step;
}

export const EVENT_CLASS: Record<DocumentEvent["status"], string> = {
  ok: "text-muted-foreground",
  warning: "text-chip-warning-fg",
  error: "text-destructive",
};

export function duration(ms: number | null): string | null {
  if (ms === null) return null;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

// For the file picker's `accept` attribute.
export function acceptAttribute(extensions: string[]): string {
  return extensions.join(",");
}

export function hasAcceptedExtension(
  filename: string,
  extensions: string[],
): boolean {
  const lower = filename.toLowerCase();
  return extensions.some((ext) => lower.endsWith(ext));
}

// Whether a drag carries files (and not, say, selected text), so the drop zone only lights up for
// something it can take.
export function dragHasFiles(types: readonly string[]): boolean {
  return types.includes("Files");
}

// Sort the library: documents being read or failed first (they need attention), then newest.
export function libraryOrder(docs: LibraryDocument[]): LibraryDocument[] {
  const rank = (d: LibraryDocument) =>
    d.status === "failed" ? 0 : isBusy(d.status) ? 1 : 2;
  return [...docs].sort(
    (a, b) => rank(a) - rank(b) || b.updated_at.localeCompare(a.updated_at),
  );
}

// What the library will call a file unless the person renames it: the file name without its
// extension and with underscores read as spaces. Mirrors the server, so the box shows what it will do.
export function defaultName(filename: string): string {
  const stem = filename.trim().replace(/\.[A-Za-z0-9]{1,8}$/, "");
  return stem.replace(/[_\s]+/g, " ").trim() || "Untitled document";
}

// Knowledge cards (Phase 8e): short facts a model drew from a document.
export const CARD_KIND_LABEL: Record<KnowledgeCardKind, string> = {
  case_study: "Case study",
  capability: "Capability",
  result: "Result",
  client: "Client",
  certification: "Certification",
  partnership: "Partnership",
};

export const CONFIDENCE_LABEL: Record<KnowledgeCardInfo["confidence"], string> =
  {
    high: "Stated plainly",
    medium: "Read between the lines",
    low: "Unsure",
  };

// "3 knowledge cards" in the library list; nothing when there are none.
export function cardsSummary(
  doc: Pick<LibraryDocument, "card_count">,
): string | null {
  const count = doc.card_count ?? 0;
  if (count === 0) return null;
  return `${formatNumber(count)} knowledge ${plural(count, "card")}`;
}

// "Written by gemini-flash-lite-latest (cards v1) · about $0.0021", for the summary.
export function summaryWrittenBy(detail: {
  summary_model?: string | null;
  summary_prompt_version?: string | null;
  summary_cost_usd?: number | null;
}): string | null {
  if (!detail.summary_model) return null;
  const prompt = detail.summary_prompt_version
    ? ` (cards ${detail.summary_prompt_version})`
    : "";
  const cost =
    typeof detail.summary_cost_usd === "number"
      ? ` · about $${detail.summary_cost_usd.toFixed(4)}`
      : "";
  return `Written by ${detail.summary_model}${prompt}${cost}`;
}
