import { useState } from "react";

import type {
  CompanyOpportunity,
  ContactRelevance,
  OfferingFit,
  Recommendation,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { briefText } from "@/features/brief/briefText";

// Copies the one-page account brief as plain text. If the browser refuses clipboard access the
// button says so instead of pretending it worked.
export function CopyBrief(props: {
  companyName: string | null;
  opportunity: CompanyOpportunity;
  fit: OfferingFit | null;
  contacts: ContactRelevance[];
  recommendation: Recommendation | null;
}) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await window.navigator.clipboard.writeText(briefText(props));
      setState("copied");
    } catch {
      setState("failed");
    }
    window.setTimeout(() => setState("idle"), 2500);
  }

  return (
    <Button type="button" size="sm" variant="outline" onClick={copy}>
      {state === "copied"
        ? "Copied"
        : state === "failed"
          ? "Could not copy"
          : "Copy brief"}
    </Button>
  );
}
