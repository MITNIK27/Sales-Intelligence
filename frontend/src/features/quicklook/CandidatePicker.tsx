import { useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Candidate } from "@/features/quicklook/api";

// Shown when the tool is not sure which company was meant, and when the person says "not this
// one". They can click the right company, paste its website, or refine the name.
export function CandidatePicker({
  candidates,
  intro,
  disabled,
  onChoose,
  onRefine,
}: {
  candidates: Candidate[];
  intro: string;
  disabled: boolean;
  onChoose: (domain: string, name: string) => void;
  onRefine: (text: string) => void;
}) {
  const [text, setText] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (text.trim()) onRefine(text.trim());
  }

  return (
    <section aria-label="Choose the company" className="mt-6">
      <h2 className="text-lg font-bold">Which company did you mean?</h2>
      <p className="mb-4 text-sm text-muted-foreground">{intro}</p>
      {candidates.length > 0 && (
        <ul className="mb-5 grid gap-3 sm:grid-cols-2">
          {candidates.map((c) => (
            <li key={c.domain}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChoose(c.domain, c.name)}
                className="group flex h-full w-full flex-col items-start gap-1 rounded-xl border border-border bg-background p-4 text-left shadow-sm transition hover:border-primary hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
              >
                <span className="flex w-full items-center justify-between gap-2 font-semibold">
                  {c.name}
                  <ArrowRight
                    className="size-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary"
                    aria-hidden="true"
                  />
                </span>
                <span className="text-sm text-primary-text">{c.domain}</span>
                {c.snippet && (
                  <span className="line-clamp-2 text-sm text-muted-foreground">
                    {c.snippet}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={submit} className="flex flex-col gap-2 sm:max-w-xl">
        <Label htmlFor="refine-company">
          {candidates.length > 0
            ? "None of these? Paste the company's website or type its full name"
            : "Paste the company's website or type its full name"}
        </Label>
        <div className="flex gap-2">
          <Input
            id="refine-company"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. infor.com or Infor Global Solutions"
            maxLength={200}
          />
          <Button type="submit" disabled={disabled || !text.trim()}>
            Look up
          </Button>
        </div>
      </form>
    </section>
  );
}
