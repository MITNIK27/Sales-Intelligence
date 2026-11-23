import { ChevronRight, FileText } from "lucide-react";
import { useState } from "react";

import { apiPost } from "@/api/client";
import type { LibraryDocument } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DocumentDetailDialog } from "@/features/documents/DocumentDetailDialog";
import { SearchBox } from "@/features/documents/SearchBox";
import { UploadZone } from "@/features/documents/UploadZone";
import {
  STATUS_CLASS,
  STATUS_LABEL,
  TYPE_LABEL,
  contentSummary,
  fileSize,
  indexingSummary,
  libraryOrder,
  pictureSummary,
} from "@/features/documents/documentLabels";
import { useDocuments } from "@/features/documents/useDocuments";
import { useOfferingOptions } from "@/features/brief/useOfferingOptions";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

// The library of decks, PDFs and notes about what we sell. What is read from them is kept (the
// files themselves are not) and is what the app will use when it matches a company to our offerings.
export function DocumentsPage() {
  const { status, documents, error, refresh } = useDocuments();
  const { options } = useOfferingOptions();
  const [openId, setOpenId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  async function readAgain(id: string) {
    setRowError(null);
    try {
      await apiPost(`/documents/${id}/reprocess`);
      await refresh();
    } catch (err) {
      setRowError(err instanceof Error ? err.message : "That did not work.");
    }
  }

  return (
    <div>
      <PageHeader
        title="Documents"
        description="Decks, PDFs and notes about what we sell. The app reads them and uses what they say when it matches companies to our offerings."
      />

      {error && <ErrorState message={error} onRetry={() => void refresh()} />}
      {!error && !status && <SkeletonLines lines={5} />}

      {status && !status.enabled && (
        <Card>
          <EmptyState
            icon={FileText}
            title="Documents are switched off"
            description="Set DOCUMENTS_ENABLED=true in backend/.env, then restart the API and the worker."
          />
        </Card>
      )}

      {status?.enabled && (
        <div className="flex flex-col gap-6">
          <UploadZone
            status={status}
            offeringOptions={options}
            onUploaded={() => void refresh()}
          />

          {documents?.some((d) => d.is_searchable) && (
            <SearchBox
              status={status}
              offeringOptions={options}
              onOpen={setOpenId}
            />
          )}

          {rowError && (
            <p className="text-sm text-destructive" role="alert">
              {rowError}
            </p>
          )}

          <Card>
            {!documents && (
              <div className="p-6">
                <SkeletonLines lines={4} />
              </div>
            )}
            {documents && documents.length === 0 && (
              <EmptyState
                icon={FileText}
                title="No documents yet"
                description="Drop a pitch deck, a capability PDF or a case study above. Nothing is kept except what it says."
              />
            )}
            {documents && documents.length > 0 && (
              <Library
                documents={libraryOrder(documents)}
                meaningSearch={status.meaning_search_enabled}
                onOpen={setOpenId}
                onReadAgain={(id) => void readAgain(id)}
              />
            )}
          </Card>
        </div>
      )}

      <DocumentDetailDialog
        documentId={openId}
        offeringOptions={options}
        onClose={() => setOpenId(null)}
        onChanged={() => void refresh()}
      />
    </div>
  );
}

function Library({
  documents,
  meaningSearch,
  onOpen,
  onReadAgain,
}: {
  documents: LibraryDocument[];
  meaningSearch: boolean;
  onOpen: (id: string) => void;
  onReadAgain: (id: string) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Document</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Contents</TableHead>
          <TableHead>About</TableHead>
          <TableHead>Updated</TableHead>
          <TableHead className="w-10">
            <span className="sr-only">Open</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.map((doc) => {
          const pictures = pictureSummary(doc.assets);
          const indexing = indexingSummary(doc, meaningSearch);
          return (
            <TableRow
              key={doc.id}
              onClick={() => onOpen(doc.id)}
              className="group cursor-pointer hover:bg-muted"
            >
              <TableCell className="max-w-80 whitespace-normal">
                <button
                  type="button"
                  className="text-left font-semibold hover:text-primary-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpen(doc.id);
                  }}
                >
                  {doc.name}
                </button>
                <div className="text-xs text-muted-foreground">
                  {TYPE_LABEL[doc.media_type]} · {fileSize(doc.size_bytes)}
                  {doc.version_count > 1 && ` · version ${doc.version}`}
                </div>
                {doc.status === "failed" && doc.error && (
                  <p className="mt-1 text-xs text-destructive">{doc.error}</p>
                )}
              </TableCell>
              <TableCell>
                <span
                  className={cn(
                    "px-2 py-0.5 text-xs font-semibold",
                    STATUS_CLASS[doc.status],
                  )}
                >
                  {STATUS_LABEL[doc.status]}
                </span>
                {doc.can_reprocess && (
                  <div className="mt-1">
                    <Button
                      type="button"
                      variant="link"
                      size="xs"
                      className="h-auto px-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        onReadAgain(doc.id);
                      }}
                    >
                      Read it again
                    </Button>
                  </div>
                )}
              </TableCell>
              <TableCell className="whitespace-normal">
                <div className="text-sm">{contentSummary(doc)}</div>
                {pictures && (
                  <div className="text-xs text-muted-foreground">
                    {pictures}
                  </div>
                )}
                {indexing && (
                  <div className="text-xs text-muted-foreground">
                    {indexing}
                  </div>
                )}
              </TableCell>
              <TableCell className="max-w-56 whitespace-normal text-sm">
                {doc.offerings.length === 0 ? (
                  <span className="text-muted-foreground">General</span>
                ) : (
                  doc.offerings.map((o) => o.name).join(", ")
                )}
              </TableCell>
              <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                {timeAgo(doc.updated_at)}
              </TableCell>
              <TableCell>
                <ChevronRight
                  className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
                  aria-hidden="true"
                />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
