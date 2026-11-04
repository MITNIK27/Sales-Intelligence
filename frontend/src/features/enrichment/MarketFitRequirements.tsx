import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Checkbox } from "@/components/Checkbox";
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
      <div>
        <h3 className="text-sm font-semibold">Criteria for this search</h3>
        <p className="text-xs text-muted-foreground">
          Optional. Type what you want checked for every company; each company
          also keeps these on its page. Switch on “Must have” to drop a company
          that clearly fails it. With nothing ticked, companies are ranked by
          how well our offerings fit and none are dropped.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium">Criteria</h4>
        <ul className="flex flex-col gap-2">
          {value.map((req) => (
            <li
              key={req.id}
              className="flex items-start gap-2 rounded-md border border-border p-2"
            >
              <span className="mt-1">
                <Checkbox
                  checked={req.include}
                  onChange={() => patch(req.id, { include: !req.include })}
                  label={`Use "${req.name}"`}
                />
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <Input
                  value={req.name}
                  onChange={(e) => patch(req.id, { name: e.target.value })}
                  className="h-8"
                />
                <Input
                  value={req.description}
                  onChange={(e) =>
                    patch(req.id, { description: e.target.value })
                  }
                  className="h-8 text-xs"
                  placeholder="What exactly must be true?"
                />
              </div>
              <label className="mt-1 flex cursor-pointer items-center gap-2 text-sm">
                <Checkbox
                  checked={req.mustHave}
                  onChange={() => patch(req.id, { mustHave: !req.mustHave })}
                  label={`Must have: ${req.name}`}
                />
                Must have
              </label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
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
            placeholder="Add a criterion, e.g. Operates a commercial fleet"
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
