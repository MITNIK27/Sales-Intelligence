import { Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { CompanyOpportunity } from "@/api/types";
import { FilterButton, type FilterOption } from "@/components/FilterButton";
import { Segmented } from "@/components/Segmented";
import { SimpleSelect } from "@/components/SimpleSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { titleCaseArea } from "@/features/brief/startBrief";
import type { FilterSource } from "@/features/brief/briefFilter";

const MAX_SEGMENTS = 4;

const SOURCE_NOTE: Record<Exclude<FilterSource, null>, string> = {
  run: "Set by the Market Discovery run",
  you: "Chosen by you",
  saved: "From your last choice",
};

function AddArea({ onAdd }: { onAdd: (label: string) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const label = draft.trim();
    if (!label) return;
    onAdd(label);
    setDraft("");
    setOpen(false);
  }

  if (!open) {
    return (
      <Button type="button" variant="action" onClick={() => setOpen(true)}>
        <Plus className="size-4" aria-hidden="true" /> Add area
      </Button>
    );
  }
  return (
    <form onSubmit={submit} className="flex items-center gap-2">
      <Input
        autoFocus
        aria-label="Area to look into"
        placeholder="e.g. data platform"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        className="h-10 w-56"
      />
      <Button type="submit" disabled={!draft.trim()}>
        Research it
      </Button>
      <Button type="button" variant="action" onClick={() => setOpen(false)}>
        Cancel
      </Button>
    </form>
  );
}

// The two choices that define a brief, always in view: which offering(s) and which area. Industry
// is shown as plain text because it is information, not a control.
export function BriefFilterBar({
  industry,
  offeringOptions,
  narrowed,
  onToggleNarrowed,
  offeringIds,
  source,
  onToggleOffering,
  onClearOfferings,
  areas,
  areaId,
  researching,
  onSelectArea,
  onAddArea,
}: {
  industry: string | null;
  offeringOptions: FilterOption[];
  // True when only the run's offerings are listed, false when all are, null when not from a run.
  narrowed: boolean | null;
  onToggleNarrowed: () => void;
  offeringIds: string[];
  source: FilterSource;
  onToggleOffering: (id: string) => void;
  onClearOfferings: () => void;
  areas: CompanyOpportunity[];
  areaId: string | null;
  researching: Set<string>;
  onSelectArea: (id: string) => void;
  onAddArea: (label: string) => void;
}) {
  const areaOptions = areas.map((a) => ({
    id: a.id,
    label: a.area_key === "general" ? "Overall" : titleCaseArea(a.area_label),
    hint: researching.has(a.id)
      ? "researching…"
      : a.status === "suggested"
        ? "suggested"
        : undefined,
  }));
  return (
    <div className="sticky top-0 z-10 -mx-1 mb-4 flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-border bg-background/95 px-1 py-3 backdrop-blur">
      <FilterButton
        label="Our offerings"
        options={offeringOptions}
        selected={offeringIds}
        onToggle={onToggleOffering}
        onClear={onClearOfferings}
        emptyText="Best match"
        showChoice={false}
        note={source ? SOURCE_NOTE[source] : null}
      />
      {offeringIds.length > 0 && (
        <ul
          aria-label="Chosen offerings"
          className="flex max-w-full flex-wrap items-center gap-1.5"
        >
          {offeringOptions
            .filter((o) => offeringIds.includes(o.id))
            .map((o) => (
              <li
                key={o.id}
                className="inline-flex items-center gap-1 bg-secondary py-0.5 pl-2 pr-0.5 text-sm text-secondary-foreground ring-1 ring-foreground/20"
              >
                <span className="max-w-48 truncate">{o.label}</span>
                <button
                  type="button"
                  aria-label={`Remove ${o.label}`}
                  onClick={() => onToggleOffering(o.id)}
                  className="inline-flex size-6 items-center justify-center hover:bg-foreground/10 focus-visible:outline-2 focus-visible:outline-primary"
                >
                  <X className="size-3.5" aria-hidden="true" />
                </button>
              </li>
            ))}
          {offeringIds.length > 1 && (
            <li>
              <button
                type="button"
                onClick={onClearOfferings}
                className="px-1 text-sm underline underline-offset-2 hover:text-primary-text"
              >
                Clear all
              </button>
            </li>
          )}
        </ul>
      )}
      {narrowed !== null && (
        <button
          type="button"
          onClick={onToggleNarrowed}
          className="text-sm text-foreground underline underline-offset-2 hover:text-primary-text"
        >
          {narrowed ? "Show all offerings" : "Only this run's offerings"}
        </button>
      )}
      {areaOptions.length > 0 &&
        (areaOptions.length <= MAX_SEGMENTS ? (
          <Segmented
            label="Opportunity area"
            options={areaOptions}
            value={areaId}
            onChange={onSelectArea}
          />
        ) : (
          <SimpleSelect
            tall
            label="Opportunity area"
            value={areaId ?? ""}
            options={areaOptions.map((o) => ({
              value: o.id,
              label: o.hint ? `${o.label} (${o.hint})` : o.label,
            }))}
            onChange={onSelectArea}
            placeholder="Choose an area"
          />
        ))}
      <AddArea onAdd={onAddArea} />
      {industry && (
        <span className="ml-auto text-sm text-muted-foreground">
          Industry: <span className="text-foreground">{industry}</span>
        </span>
      )}
    </div>
  );
}
