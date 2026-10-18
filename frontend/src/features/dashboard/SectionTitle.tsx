import type { ReactNode } from "react";

import { CardTitle } from "@/components/ui/card";

// Card titles render as a div; this makes them real level-2 headings for screen readers and
// keeps the visual size consistent across the dashboard.
export function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <CardTitle
      role="heading"
      aria-level={2}
      className="text-base font-semibold"
    >
      {children}
    </CardTitle>
  );
}
