import { FileText, FileUp, Loader2, X } from "lucide-react";
import { useRef, useState, type ComponentRef, type DragEvent } from "react";

import { apiUpload } from "@/api/client";
import type { DocumentsStatusInfo, LibraryDocument } from "@/api/types";
import { Checkbox } from "@/components/Checkbox";
import { FilterButton, type FilterOption } from "@/components/FilterButton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  acceptAttribute,
  defaultName,
  dragHasFiles,
  fileSize,
  hasAcceptedExtension,
} from "@/features/documents/documentLabels";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

type Staged = { key: number; file: File; name: string };

type Result = {
  key: number;
  name: string;
  state: "uploading" | "queued" | "refused";
  message?: string;
};

// Choosing or dropping files only lines them up. Nothing is uploaded or read until you press Read,
// so you can rename them, say which offerings they are about, and decide whether pictures should be
// described by AI (which spends model quota) before anything starts. Each file is then sent on its
// own, so one refusal never stops the others, and every file gets its own line saying what happened.
export function UploadZone({
  status,
  offeringOptions,
  onUploaded,
}: {
  status: DocumentsStatusInfo;
  offeringOptions: FilterOption[];
  onUploaded: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [staged, setStaged] = useState<Staged[]>([]);
  const [offerings, setOfferings] = useState<string[]>([]);
  const [describe, setDescribe] = useState(false);
  const [results, setResults] = useState<Result[]>([]);
  const input = useRef<ComponentRef<"input">>(null);
  const counter = useRef(0);
  const busy = results.some((r) => r.state === "uploading");

  function stage(files: File[]) {
    const refused: Result[] = [];
    const accepted: Staged[] = [];
    for (const file of files) {
      if (!hasAcceptedExtension(file.name, status.accepted_extensions)) {
        refused.push({
          key: counter.current++,
          name: file.name,
          state: "refused",
          message: `This type of file is not supported. Use ${status.accepted_extensions.join(", ")}.`,
        });
      } else if (file.size > status.max_upload_mb * 1024 * 1024) {
        refused.push({
          key: counter.current++,
          name: file.name,
          state: "refused",
          message: `This file is ${fileSize(file.size)}, over the ${status.max_upload_mb} MB limit.`,
        });
      } else if (
        !staged.some(
          (s) => s.file.name === file.name && s.file.size === file.size,
        )
      ) {
        accepted.push({
          key: counter.current++,
          file,
          name: defaultName(file.name),
        });
      }
    }
    if (accepted.length > 0) setStaged((current) => [...current, ...accepted]);
    if (refused.length > 0) setResults((current) => [...refused, ...current]);
  }

  function patchResult(key: number, change: Partial<Result>) {
    setResults((current) =>
      current.map((r) => (r.key === key ? { ...r, ...change } : r)),
    );
  }

  async function readStaged() {
    const batch = staged;
    const chosen = offerings;
    const describePictures = describe;
    setStaged([]);
    setResults((current) => [
      ...batch.map((s): Result => ({
        key: s.key,
        name: s.name,
        state: "uploading",
      })),
      ...current,
    ]);
    for (const item of batch) {
      const form = new FormData();
      form.append("file", item.file);
      if (item.name.trim()) form.append("name", item.name.trim());
      for (const id of chosen) form.append("product_ids", id);
      if (status.vision_enabled)
        form.append("describe_pictures", describePictures ? "true" : "false");
      try {
        await apiUpload<LibraryDocument>("/documents", form);
        patchResult(item.key, { state: "queued" });
        onUploaded();
      } catch (err) {
        patchResult(item.key, {
          state: "refused",
          message: err instanceof Error ? err.message : "Upload failed.",
        });
      }
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) stage(files);
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div
          onDragOver={(e) => {
            if (!dragHasFiles(Array.from(e.dataTransfer.types))) return;
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "flex flex-col items-center gap-3 border-2 border-dashed px-6 py-8 text-center transition-colors",
            dragging
              ? "border-primary bg-primary/5"
              : "border-border bg-card hover:border-primary/60",
          )}
        >
          <FileUp className="size-8 text-muted-foreground" aria-hidden="true" />
          <div>
            <p className="text-base font-bold">
              Drop files here, or choose them
            </p>
            <p className="text-sm text-muted-foreground">
              Decks, PDFs, Word and Markdown or text files, up to{" "}
              {status.max_upload_mb} MB each. Nothing is read until you confirm,
              and the app keeps what the file says, not the file itself.
            </p>
          </div>
          <input
            ref={input}
            type="file"
            multiple
            accept={acceptAttribute(status.accepted_extensions)}
            className="sr-only"
            aria-label="Choose files to upload"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = "";
              if (files.length > 0) stage(files);
            }}
          />
          <Button
            type="button"
            variant="action"
            onClick={() => input.current?.click()}
          >
            Choose files
          </Button>
        </div>

        {staged.length > 0 && (
          <section
            aria-label="Ready to read"
            className="flex flex-col gap-4 border-t border-border pt-5"
          >
            <div>
              <h3 className="text-base font-bold">
                Ready to read
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {staged.length} {plural(staged.length, "file")}
                </span>
              </h3>
              <p className="text-sm text-muted-foreground">
                Check the names and settings, then press Read. Nothing has been
                uploaded yet.
              </p>
            </div>

            <ul className="flex flex-col gap-2">
              {staged.map((item) => (
                <li
                  key={item.key}
                  className="flex w-fit max-w-full items-center gap-3 border border-border p-3"
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10">
                    <FileText
                      className="size-5 text-primary-text"
                      aria-hidden="true"
                    />
                  </span>
                  <div className="flex w-72 min-w-0 max-w-full flex-col gap-1 sm:w-96">
                    <Input
                      aria-label={`Name for ${item.file.name}`}
                      value={item.name}
                      maxLength={255}
                      onChange={(e) =>
                        setStaged((current) =>
                          current.map((s) =>
                            s.key === item.key
                              ? { ...s, name: e.target.value }
                              : s,
                          ),
                        )
                      }
                      className="h-9 w-full max-w-sm"
                    />
                    <span className="truncate text-xs text-muted-foreground">
                      {item.file.name} · {fileSize(item.file.size)}
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${item.file.name}`}
                    onClick={() =>
                      setStaged((current) =>
                        current.filter((s) => s.key !== item.key),
                      )
                    }
                  >
                    <X aria-hidden="true" />
                  </Button>
                </li>
              ))}
            </ul>

            <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
              <FilterButton
                label="About"
                options={offeringOptions}
                selected={offerings}
                onToggle={(id) =>
                  setOfferings((cur) =>
                    cur.includes(id)
                      ? cur.filter((x) => x !== id)
                      : [...cur, id],
                  )
                }
                onClear={() => setOfferings([])}
                emptyText="General (any offering)"
                note="Tie these files to the offerings they describe, or leave it general for something like a company deck."
              />
              {status.vision_enabled && (
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={describe}
                    onChange={() => setDescribe((v) => !v)}
                    label="Describe pictures and scanned pages with AI"
                  />
                  <span>
                    Describe pictures and scanned pages with AI{" "}
                    <span className="text-muted-foreground">
                      (uses Gemini quota)
                    </span>
                  </span>
                </label>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" onClick={() => void readStaged()}>
                Read{" "}
                {staged.length === 1
                  ? "this file"
                  : `these ${staged.length} files`}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setStaged([])}
              >
                Cancel
              </Button>
            </div>
          </section>
        )}

        {results.length > 0 && (
          <ul className="flex flex-col gap-2" aria-live="polite">
            {results.map((row) => (
              <li
                key={row.key}
                className="flex items-start gap-2 text-sm"
                data-state={row.state}
              >
                {row.state === "uploading" && (
                  <Loader2
                    className="mt-0.5 size-4 shrink-0 animate-spin motion-reduce:animate-none"
                    aria-hidden="true"
                  />
                )}
                <span className="font-medium">{row.name}</span>
                <span
                  className={cn(
                    row.state === "refused"
                      ? "text-destructive"
                      : "text-muted-foreground",
                  )}
                >
                  {row.state === "uploading" && "Uploading…"}
                  {row.state === "queued" &&
                    "Uploaded. It is being read now; this can take a minute."}
                  {row.state === "refused" && row.message}
                </span>
              </li>
            ))}
          </ul>
        )}
        {results.length > 0 && !busy && (
          <div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setResults([])}
            >
              Clear this list
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
