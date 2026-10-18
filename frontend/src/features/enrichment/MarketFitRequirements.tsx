import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type Requirement = {
  id: string;
  name: string;
  description: string;
  include: boolean;
};

let counter = 0;
function newId(): string {
  counter += 1;
  return `req-${Date.now()}-${counter}`;
}

// Starting points built from what the search was parsed into. Industry and location are on by
// default; size is offered but off, because employee counts are often missing from the data and
// an unverifiable hard requirement would leave a company "needs evidence" instead of passing.
export function seedRequirements(
  industryKeywords: string,
  location: string,
  employeeSizeRange: string,
): Requirement[] {
  const seeds: Requirement[] = [];
  if (industryKeywords.trim()) {
    seeds.push({
      id: newId(),
      name: "Operates in the target industry",
      description: `The company's main business is in: ${industryKeywords.trim()}.`,
      include: true,
    });
  }
  if (location.trim()) {
    seeds.push({
      id: newId(),
      name: "Operates in the target location",
      description: `The company has its headquarters or significant operations in ${location.trim()}.`,
      include: true,
    });
  }
  if (employeeSizeRange.trim()) {
    seeds.push({
      id: newId(),
      name: "Company size in range",
      description: `The company has about ${employeeSizeRange.trim()} employees.`,
      include: false,
    });
  }
  return seeds;
}

export function toRequestCriteria(requirements: Requirement[]) {
  return requirements
    .filter((r) => r.include && r.name.trim())
    .map((r) => ({ name: r.name.trim(), description: r.description.trim() || null }));
}

// The hard requirements for THIS search. Each is checked against real evidence for every
// company; a company that clearly fails one is rejected, one that can't be verified is flagged.
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
    onChange([...value, { id: newId(), name: name.trim(), description: description.trim(), include: true }]);
    setName("");
    setDescription("");
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold">Hard requirements for this search</h3>
        <p className="text-xs text-muted-foreground">
          Every company is checked against these using real evidence. One that clearly fails is
          rejected; one that can't be verified is flagged "needs evidence" — never assumed to pass.
        </p>
      </div>

      {value.length === 0 && (
        <p className="text-sm text-muted-foreground">
          None yet — without any, nothing can be rejected as a poor market fit.
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {value.map((req) => (
          <li key={req.id} className="flex items-start gap-2 rounded-md border border-border p-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={req.include}
              aria-label={`Use "${req.name}"`}
              onChange={(e) =>
                onChange(value.map((r) => (r.id === req.id ? { ...r, include: e.target.checked } : r)))
              }
            />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <Input
                value={req.name}
                onChange={(e) =>
                  onChange(value.map((r) => (r.id === req.id ? { ...r, name: e.target.value } : r)))
                }
                className="h-8"
              />
              <Input
                value={req.description}
                onChange={(e) =>
                  onChange(
                    value.map((r) => (r.id === req.id ? { ...r, description: e.target.value } : r)),
                  )
                }
                className="h-8 text-xs"
                placeholder="What exactly must be true?"
              />
            </div>
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
          placeholder="Add a requirement, e.g. Operates a commercial fleet"
          className="h-8"
        />
        <Input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Details (optional)"
          className="h-8"
        />
        <Button type="button" variant="outline" size="sm" onClick={add} disabled={!name.trim()}>
          <Plus className="size-4" /> Add
        </Button>
      </div>
    </div>
  );
}
