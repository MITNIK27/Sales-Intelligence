import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Checkbox } from "@/components/Checkbox";
import { Segmented } from "@/components/Segmented";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  newRequirementId,
  type Requirement,
} from "@/features/enrichment/runCriteria";

// The criteria for THIS search. Nothing is applied unless it is ticked here. A ticked criterion is
// checked against real evidence for every company; one marked "Must have" also drops a company
// that clearly fails it (one that cannot be verified is flagged, never assumed to pass).
export function MarketFitRequirements({
  value,
  onChange,
}: {
  value: Requirement[];
  onChange: (next: Requirement[]) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  function add() {
    if (!name.trim()) return;
    onChange([
      ...value,
      {
        id: newRequirementId(),
        name: name.trim(),
        description: description.trim(),
        include: true,
        mustHave: false,
      },
    ]);
    setName("");
    setDescription("");
  }

  function patch(id: string, change: Partial<Requirement>) {
    onChange(value.map((r) => (r.id === id ? { ...r, ...change } : r)));
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        {value.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No checks yet. Add one below, for example "Operates a commercial
            fleet".
          </p>
        )}
        <ul className="flex flex-col gap-3">
          {value.map((req) => (
            <li
              key={req.id}
              className={`flex items-start gap-3 border border-border bg-background p-3 transition-opacity ${req.include ? "" : "opacity-60"}`}
            >
              <span className="mt-7">
                <Checkbox
                  checked={req.include}
                  onChange={() =>
                    patch(
                      req.id,
                      req.include
                        ? { include: false, mustHave: false }
                        : { include: true },
                    )
                  }
                  label={`Use "${req.name}"`}
                />
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-muted-foreground">
                    Check
                  </span>
                  <Input
                    value={req.name}
                    onChange={(e) => patch(req.id, { name: e.target.value })}
                    className="h-9 bg-card font-semibold"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-muted-foreground">
                    Details
                  </span>
                  <Input
                    value={req.description}
                    onChange={(e) =>
                      patch(req.id, { description: e.target.value })
                    }
                    className="h-9 bg-card text-sm"
                    placeholder="What exactly must be true?"
                  />
                </label>
              </div>
              <div className="flex shrink-0 flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">
                  How strict
                </span>
                <Segmented
                  label={`How strict: ${req.name}`}
                  disabled={!req.include}
                  value={req.mustHave ? "must" : "nice"}
                  onChange={(id) => patch(req.id, { mustHave: id === "must" })}
                  options={[
                    { id: "nice", label: "Nice to have" },
                    { id: "must", label: "Must have" },
                  ]}
                />
                <span className="max-w-56 text-xs text-muted-foreground">
                  {!req.include
                    ? "Tick the check to set this."
                    : req.mustHave
                      ? "Drops companies that clearly fail it."
                      : "Only helps rank. Never drops a company."}
                </span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-6"
                aria-label={`Remove "${req.name}"`}
                onClick={() => onChange(value.filter((r) => r.id !== req.id))}
              >
                <X className="size-4" />
              </Button>
            </li>
          ))}
        </ul>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Add a check, e.g. Operates a commercial fleet"
            className="h-8"
          />
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Details (optional)"
            className="h-8"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={add}
            disabled={!name.trim()}
          >
            <Plus className="size-4" /> Add
          </Button>
        </div>
      </div>
    </div>
  );
}
