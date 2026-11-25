import { X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import {
  addPlace,
  MAX_PLACES,
  removePlace,
} from "@/features/enrichment/places";

// Where the companies should be: one chip per place. Type a place and press Enter (or a comma) to
// add it; Backspace in the empty box removes the last one. Leaving it empty searches anywhere.
export function PlacesInput({
  id,
  places,
  onChange,
}: {
  id: string;
  places: string[];
  onChange: (places: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const full = places.length >= MAX_PLACES;

  function commit() {
    if (!draft.trim()) return;
    onChange(addPlace(places, draft));
    setDraft("");
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Enter" || e.key === "," || e.key === ";") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && places.length > 0) {
      onChange(places.slice(0, -1));
    }
  }

  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input bg-transparent px-2 py-1 shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
      {places.map((place) => (
        <span
          key={place}
          className="inline-flex items-center gap-1 rounded-sm bg-secondary py-0.5 pl-2 pr-1 text-sm"
        >
          {place}
          <button
            type="button"
            onClick={() => onChange(removePlace(places, place))}
            className="rounded-sm p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
            aria-label={`Remove ${place}`}
          >
            <X className="size-3.5" aria-hidden="true" />
          </button>
        </span>
      ))}
      <input
        id={id}
        type="text"
        value={draft}
        disabled={full}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        placeholder={
          full
            ? `Up to ${MAX_PLACES} places`
            : places.length === 0
              ? "e.g. Germany, then press Enter"
              : "Add another place"
        }
        className="h-7 min-w-32 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
      />
    </div>
  );
}
