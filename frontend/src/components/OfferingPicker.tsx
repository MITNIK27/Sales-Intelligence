import { useState } from "react";

import type { Product } from "@/api/types";
import { OfferingSelectItems } from "@/components/OfferingSelectItems";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BAND_LABEL } from "@/features/brief/opportunityLabels";
import type { SuggestedOffering } from "@/features/companies/lib/suggestedOfferings";
import { cn } from "@/lib/utils";

const PAGE = 7;

// Pick one of our offerings. Offerings already researched for this company come first, with how
// well each fits; the rest of the catalogue follows (or is left out when `onlyResearched` is set
// and there is something researched). The list shows seven at a time and loads the next seven as
// you scroll to the bottom.
export function OfferingPicker({
  products,
  researched,
  value,
  onChange,
  onlyResearched = false,
  className,
  label = "Offering",
  placeholder = "Select an offering…",
}: {
  products: Product[];
  researched: SuggestedOffering[];
  value: string;
  onChange: (productId: string) => void;
  onlyResearched?: boolean;
  className?: string;
  label?: string;
  placeholder?: string;
}) {
  const [shown, setShown] = useState(PAGE);
  const researchedIds = new Set(researched.map((r) => r.product.id));
  const rest =
    onlyResearched && researched.length > 0
      ? []
      : products.filter((p) => !researchedIds.has(p.id));

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        className={cn("h-10 min-w-48 bg-card", className)}
        aria-label={label}
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {/* The list scrolls inside this box: the dropdown sizes itself to the screen, so a class
            on the dropdown itself is overridden and the full list would show. */}
        <div
          className="max-h-60 overflow-y-auto"
          onScroll={(e) => {
            const box = e.currentTarget;
            if (box.scrollHeight - box.scrollTop - box.clientHeight < 24)
              setShown((n) => Math.min(n + PAGE, rest.length));
          }}
        >
          {researched.length > 0 && (
            <>
              <SelectGroup>
                <SelectLabel>Researched for this company</SelectLabel>
                {researched.map((r) => (
                  <SelectItem key={r.product.id} value={r.product.id}>
                    {r.product.name}
                    <span className="ml-2 text-xs text-muted-foreground">
                      {BAND_LABEL[r.band]}
                    </span>
                  </SelectItem>
                ))}
              </SelectGroup>
              {rest.length > 0 && <SelectSeparator />}
            </>
          )}
          <OfferingSelectItems products={rest.slice(0, shown)} />
        </div>
      </SelectContent>
    </Select>
  );
}
