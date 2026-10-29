import type { Product } from "@/api/types";
import { SelectGroup, SelectItem, SelectLabel } from "@/components/ui/select";
import { KIND_LABEL_PLURAL, groupByKind } from "@/lib/offerings";

// The options for an offering dropdown: services first, then products. Headings only appear when
// both kinds exist, so a catalog of one kind stays a plain list.
export function OfferingSelectItems({ products }: { products: Product[] }) {
  const groups = groupByKind(products);
  return (
    <>
      {groups.map((group) => (
        <SelectGroup key={group.kind}>
          {groups.length > 1 && <SelectLabel>{KIND_LABEL_PLURAL[group.kind]}</SelectLabel>}
          {group.items.map((product) => (
            <SelectItem key={product.id} value={product.id}>
              {product.name}
            </SelectItem>
          ))}
        </SelectGroup>
      ))}
    </>
  );
}
