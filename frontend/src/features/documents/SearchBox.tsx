import { Loader2, Search } from "lucide-react";
import { useState, type FormEvent } from "react";

import { apiGet } from "@/api/client";
import type { DocumentSearchResult, DocumentsStatusInfo } from "@/api/types";
import { FilterButton, type FilterOption } from "@/components/FilterButton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DocumentText } from "@/features/documents/DocumentText";
import { matchLabel } from "@/features/documents/documentLabels";
import { plural } from "@/lib/format";

// Ask the library a question. Passages come back with where they are from (document and slide or
// page) and how they were found, so a person can judge them and the app can later quote them.
export function SearchBox({
  status,
  offeringOptions,
  onOpen,
}: {
  status: DocumentsStatusInfo;
  offeringOptions: FilterOption[];
  onOpen: (documentId: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const [offerings, setOfferings] = useState<string[]>([]);
  const [result, setResult] = useState<DocumentSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const q = question.trim();
    if (!q || searching) return;
    setSearching(true);
    setError(null);
    try {
      const params = new URLSearchParams({ q });
      for (const id of offerings) params.append("product_id", id);
      setResult(
        await apiGet<DocumentSearchResult>(`/documents/search?${params}`),
      );
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "The search failed.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div>
          <h2 className="text-base font-bold">Search the documents</h2>
          <p className="text-sm text-muted-foreground">
            Ask in your own words, for example "how do we reduce development
            cost?".{" "}
            {status.meaning_search_enabled
              ? "Passages are found by meaning and by exact words."
              : "Passages are found by their words (meaning search is switched off)."}
          </p>
        </div>

        <form
          onSubmit={(e) => void submit(e)}
          className="flex flex-wrap items-center gap-3"
        >
          <div className="relative min-w-64 flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              aria-label="Search the documents"
              placeholder="What do you want to know?"
              value={question}
              maxLength={500}
              onChange={(e) => setQuestion(e.target.value)}
              className="h-10 pl-9"
            />
          </div>
          <FilterButton
            label="About"
            options={offeringOptions}
            selected={offerings}
            onToggle={(id) =>
              setOfferings((cur) =>
                cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id],
              )
            }
            onClear={() => setOfferings([])}
            emptyText="Any offering"
            note="Only documents about these offerings, plus general ones, are searched."
          />
          <Button type="submit" disabled={!question.trim() || searching}>
            {searching ? (
              <Loader2
                className="size-4 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            ) : null}
            Search
          </Button>
        </form>

        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        {result && (
          <div className="flex flex-col gap-3" aria-live="polite">
            {result.note && (
              <p className="text-sm text-muted-foreground">{result.note}</p>
            )}
            {result.hits.length === 0 ? (
              <p className="text-sm">
                Nothing in the documents answers that. Try other words, or add a
                document that covers it.
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                {result.hits.length} {plural(result.hits.length, "passage")},
                best first.
              </p>
            )}
            <ol className="flex flex-col gap-3">
              {result.hits.map((hit) => (
                <li
                  key={hit.chunk_id}
                  className="flex flex-col gap-2 border border-border p-3"
                >
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <button
                      type="button"
                      className="text-left font-semibold hover:text-primary-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                      onClick={() => onOpen(hit.document_id)}
                    >
                      {hit.document_name}
                    </button>
                    <span className="text-sm text-muted-foreground">
                      {hit.locator}
                      {hit.heading_path ? ` · ${hit.heading_path}` : ""}
                    </span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {matchLabel(hit)}
                    </span>
                  </div>
                  <DocumentText text={hit.text} />
                  {hit.offerings.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      About {hit.offerings.map((o) => o.name).join(", ")}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
