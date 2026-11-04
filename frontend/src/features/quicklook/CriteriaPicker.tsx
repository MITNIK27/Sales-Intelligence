import { useState, type FormEvent } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  MAX_CRITERIA,
  MAX_CRITERION_CHARS,
  addCustom,
  allCriteria,
  removeCustom,
  type Extras,
} from "@/features/quicklook/extras";

// Type the criteria to check a company against. Nothing here is applied unless typed.
export function CriteriaPicker({
  extras,
  onChange,
}: {
  extras: Extras;
  onChange: (next: Extras) => void;
}) {
  const [typed, setTyped] = useState("");
  const count = allCriteria(extras).length;

  function add(e: FormEvent) {
    e.preventDefault();
    onChange(addCustom(extras, typed));
    setTyped("");
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-sm font-medium">
        Criteria to check (optional)
        {count > 0 && (
          <span className="ml-2 font-normal text-muted-foreground">
            {count} of {MAX_CRITERIA} chosen
          </span>
        )}
      </legend>

      <form onSubmit={add} className="flex gap-2 sm:max-w-xl">
        <Input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="e.g. Is expanding into new markets"
          maxLength={MAX_CRITERION_CHARS}
          aria-label="Add your own criterion"
        />
        <Button
          type="submit"
          variant="outline"
          disabled={!typed.trim() || count >= MAX_CRITERIA}
        >
          Add
        </Button>
      </form>

      {extras.custom.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {extras.custom.map((c) => (
            <li
              key={c}
              className="inline-flex items-center gap-1 rounded-full bg-secondary py-1 pl-3 pr-1 text-sm"
            >
              {c}
              <button
                type="button"
                onClick={() => onChange(removeCustom(extras, c))}
                aria-label={`Remove ${c}`}
                className="grid size-6 place-items-center rounded-full hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}
