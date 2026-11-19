import { Check, ChevronDown, Search } from "lucide-react";
import { useRef, useState, type ComponentRef } from "react";

import type { Product } from "@/api/types";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { BAND_LABEL } from "@/features/brief/opportunityLabels";
import {
  DRAFT_SOURCE_HEADING,
  type DraftOffering,
  type DraftSource,
} from "@/features/companies/lib/draftOfferings";
import { cn } from "@/lib/utils";

const MAX_RESULTS = 8;
const SOURCES: DraftSource[] = ["search", "brief", "fit"];

// Pick the offering a draft is written about. With nothing typed, the list is what applies to this
// company: what the rep searched for in Market Discovery, what they made a brief around, and what the
// Brief found a strong or possible fit for. Typing searches all of our offerings by name, for the
// times a rep wants to write about something none of that points to.
export function OfferingSearchPicker({
  products,
  options,
  value,
  onChange,
  className,
  label = "Offering",
}: {
  products: Product[];
  options: DraftOffering[];
  value: string;
  onChange: (productId: string) => void;
  className?: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const input = useRef<ComponentRef<"input">>(null);

  const known = new Map(options.map((o) => [o.product.id, o]));
  const selected = products.find((p) => p.id === value) ?? null;
  const selectedBand = selected ? known.get(selected.id)?.band : null;
  const text = query.trim().toLowerCase();
  const found = text
    ? products
        .filter((p) => p.name.toLowerCase().includes(text))
        .slice(0, MAX_RESULTS)
    : [];
  const first = text ? found[0]?.id : options[0]?.product.id;

  function choose(id: string) {
    onChange(id);
    setOpen(false);
    setQuery("");
  }

  function row(p: Product, band: DraftOffering["band"] | undefined) {
    return (
      <li key={p.id} role="option" aria-selected={p.id === value}>
        <button
          type="button"
          onClick={() => choose(p.id)}
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
        >
          <span className="min-w-0 flex-1 truncate">{p.name}</span>
          {band && (
            <span className="shrink-0 text-xs text-muted-foreground">
              {BAND_LABEL[band]}
            </span>
          )}
          {p.id === value && (
            <Check className="size-4 shrink-0" aria-hidden="true" />
          )}
        </button>
      </li>
    );
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`${label}: ${selected?.name ?? "none chosen"}`}
          className={cn(
            "inline-flex h-10 min-w-56 items-center justify-between gap-2 border border-border bg-card px-3 text-sm",
            "shadow-xs transition-colors hover:border-primary hover:bg-muted",
            "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary",
            className,
          )}
        >
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate">
              {selected ? selected.name : "Choose an offering…"}
            </span>
            {selectedBand && (
              <span className="shrink-0 text-xs text-muted-foreground">
                {BAND_LABEL[selectedBand]}
              </span>
            )}
          </span>
          <ChevronDown
            className="size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-96 p-0"
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          input.current?.focus();
        }}
      >
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search
            className="size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            ref={input}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && first) {
                e.preventDefault();
                choose(first);
              }
            }}
            placeholder="Type to search all our offerings"
            aria-label="Search our offerings"
            className="h-10 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>

        <div className="max-h-72 overflow-y-auto pb-1">
          {text ? (
            <>
              <p className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                All our offerings
              </p>
              <ul role="listbox" aria-label={label}>
                {found.map((p) => row(p, known.get(p.id)?.band))}
              </ul>
              {found.length === 0 && (
                <p className="px-3 pb-3 pt-1 text-sm text-muted-foreground">
                  No offering of ours matches &ldquo;{query.trim()}&rdquo;.
                  Drafts are written around our offerings, so add it under
                  Offerings first.
                </p>
              )}
            </>
          ) : options.length === 0 ? (
            <p className="px-3 pb-3 pt-2 text-sm text-muted-foreground">
              Nothing has been searched, briefed or matched for this company
              yet. Type to search all of our offerings.
            </p>
          ) : (
            SOURCES.map((source) => {
              const group = options.filter((o) => o.source === source);
              if (group.length === 0) return null;
              return (
                <div key={source}>
                  <p className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {DRAFT_SOURCE_HEADING[source]}
                  </p>
                  <ul role="listbox" aria-label={DRAFT_SOURCE_HEADING[source]}>
                    {group.map((o) => row(o.product, o.band))}
                  </ul>
                </div>
              );
            })
          )}
        </div>
        {!text && options.length > 0 && (
          <p className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
            Weaker fits are left out. Type to find any other offering.
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}
