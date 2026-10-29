import { ChevronDown } from "lucide-react";

import type { RoleCategory } from "@/api/types";
import { Checkbox } from "@/components/Checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

// Same shape as the offerings picker: a button that opens a checklist, so a long list never takes
// room on the page. Choosing nothing is a real answer here — it means every role is a target.
export function roleSelectionSummary(categories: RoleCategory[], selectedIds: Set<string>): string {
  const chosen = categories.filter((category) => selectedIds.has(category.id));
  if (chosen.length === 0) return "All roles";
  if (chosen.length === 1) return chosen[0].name;
  return `${chosen.length} roles selected`;
}

export function RoleCategoryMultiSelect({
  categories,
  selectedIds,
  onToggle,
}: {
  categories: RoleCategory[];
  selectedIds: Set<string>;
  onToggle: (categoryId: string) => void;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Target roles to focus on"
          className="flex h-8 max-w-64 items-center gap-2 border border-border bg-card px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary"
        >
          <span className="truncate">{roleSelectionSummary(categories, selectedIds)}</span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start">
        <div className="flex max-h-72 flex-col gap-2 overflow-y-auto p-3">
          {categories.map((category) => (
            <label key={category.id} className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={selectedIds.has(category.id)}
                onChange={() => onToggle(category.id)}
                label={category.name}
              />
              <span>{category.name}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
