import type { Product } from "@/api/types";
import { Checkbox } from "@/components/Checkbox";

// No multi-select dropdown primitive exists in this project's ui kit yet, and with typically only
// a handful of products configured, a plain checklist (reusing the existing Checkbox component,
// the same one used for row-selection elsewhere) is simpler than introducing a new one. One
// product means there's nothing to choose between — callers should auto-select it and skip
// rendering this entirely rather than show a single disabled checkbox.
export function ProductMultiSelect({
  products,
  selectedIds,
  onToggle,
}: {
  products: Product[];
  selectedIds: Set<string>;
  onToggle: (productId: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2 border border-border bg-card p-3">
      {products.map((product) => (
        // A native <label> wrapping the input forwards a click anywhere in it to the checkbox,
        // so this gives a clickable product name without needing an id to wire up htmlFor.
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
  );
}
