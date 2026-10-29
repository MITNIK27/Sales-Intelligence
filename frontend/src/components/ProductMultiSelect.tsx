import { ChevronDown } from "lucide-react";

import type { Product } from "@/api/types";
import { Checkbox } from "@/components/Checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { KIND_LABEL_PLURAL, groupByKind, selectionSummary } from "@/lib/offerings";

// A button that opens the checklist, so the choice never takes room on the page: with dozens of
// offerings an always-open list covered the screen. One offering means there's nothing to choose
// between — callers should auto-select it and skip rendering this entirely. When both services and
// products exist they are listed under their own headings, and the list scrolls inside the popover.
export function ProductMultiSelect({
  products,
  selectedIds,
  onToggle,
}: {
  products: Product[];
  selectedIds: Set<string>;
  onToggle: (productId: string) => void;
}) {
  const groups = groupByKind(products);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Offerings to pitch"
          className="flex h-8 max-w-64 items-center gap-2 border border-border bg-card px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary"
        >
          <span className="truncate">{selectionSummary(products, selectedIds)}</span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <div className="flex max-h-72 flex-col gap-3 overflow-y-auto p-3">
          {groups.map((group) => (
            <div key={group.kind} className="flex flex-col gap-2">
              {groups.length > 1 && (
                <p className="text-xs font-semibold text-muted-foreground">
                  {KIND_LABEL_PLURAL[group.kind]}
                </p>
              )}
              {group.items.map((product) => (
                // A native <label> wrapping the input forwards a click anywhere in it to the
                // checkbox, so this gives a clickable name without needing an id for htmlFor.
                <label key={product.id} className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={selectedIds.has(product.id)}
                    onChange={() => onToggle(product.id)}
                    label={product.name}
                  />
                  <span>{product.name}</span>
                </label>
              ))}
            </div>
          ))}
        </div>
        <p className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
          Used to write drafts for the contacts you confirm.
        </p>
      </PopoverContent>
    </Popover>
  );
}
