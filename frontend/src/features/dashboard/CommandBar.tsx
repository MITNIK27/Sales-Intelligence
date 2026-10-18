import { ArrowRight, Search } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";

const EXAMPLES = [
  "Logistics and parcel delivery companies in Germany, France and the Netherlands, 1,000-10,000 employees",
  "Mid-size retail banks in the Nordics, 500-5,000 employees",
];

function short(text: string): string {
  return text.length > 56 ? `${text.slice(0, 54)}…` : text;
}

// The one primary action on the page: describe a market and start. The text is handed to Market
// Discovery, which parses it and shows the confirm step, so a rep starts here without hunting
// through the sidebar.
export function CommandBar({ recentSearches }: { recentSearches: string[] }) {
  const [text, setText] = useState("");
  const navigate = useNavigate();

  function start(prompt: string) {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    navigate("/market-discovery", { state: { prompt: trimmed } });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    start(text);
  }

  // One quiet row: your latest searches to run again, or two examples for someone new.
  const chips =
    recentSearches.length > 0 ? recentSearches.slice(0, 2) : EXAMPLES;
  const chipsLabel = recentSearches.length > 0 ? "Run again" : "Try";

  return (
    <section
      aria-label="Start a search"
      className="border border-border bg-card p-4"
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="dashboard-search" className="sr-only">
          Describe the market you want to find prospects in
        </label>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
          <input
            id="dashboard-search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe a market to find prospects, e.g. SaaS companies in Bangalore, 50-200 employees"
            className="h-11 w-full border border-input bg-background pl-11 pr-3 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          />
        </div>
        <Button
          type="submit"
          size="lg"
          disabled={!text.trim()}
          className="h-11 px-6"
        >
          Find prospects <ArrowRight className="size-4" />
        </Button>
      </form>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">{chipsLabel}:</span>
        {chips.map((chip) => (
          <button
            key={chip}
            type="button"
            onClick={() =>
              recentSearches.length > 0 ? start(chip) : setText(chip)
            }
            className="max-w-full truncate border border-border px-2 py-1 text-left text-muted-foreground transition-colors duration-200 hover:border-primary hover:text-foreground"
            title={chip}
          >
            {short(chip)}
          </button>
        ))}
      </div>
    </section>
  );
}
