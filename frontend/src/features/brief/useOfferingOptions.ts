import { useEffect, useMemo, useState } from "react";

import { apiGet } from "@/api/client";
import type { Product, ProductList } from "@/api/types";
import type { FilterOption } from "@/components/FilterButton";
import { KIND_LABEL_PLURAL, kindOf } from "@/lib/offerings";

// The offerings a person can filter by: the active ones, grouped as services and products. A
// failed load leaves the list empty, which the filter shows as "no offerings", never as an error.
export function useOfferingOptions(): {
  products: Product[] | null;
  options: FilterOption[];
  known: Set<string> | null;
} {
  const [products, setProducts] = useState<Product[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<ProductList>("/products?limit=200")
      .then((list) => !cancelled && setProducts(list.items))
      .catch(() => !cancelled && setProducts([]));
    return () => {
      cancelled = true;
    };
  }, []);

  const options = useMemo(
    () =>
      (products ?? [])
        .filter((p) => p.status === "active")
        .map((p) => ({
          id: p.id,
          label: p.name,
          group: KIND_LABEL_PLURAL[kindOf(p)],
        })),
    [products],
  );
  const known = useMemo(
    () => (products ? new Set(options.map((o) => o.id)) : null),
    [products, options],
  );
  return { products, options, known };
}
