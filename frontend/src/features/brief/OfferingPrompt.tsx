import { useState } from "react";

import { Button } from "@/components/ui/button";
import { titleCaseArea, type BriefTarget } from "@/features/brief/startBrief";

// Asked when an offering is chosen that nothing has been looked at for yet. Saying yes makes its
// own area, a separate section of the brief researched around that offering, so each offering
// gets its own page to switch between.
export function OfferingPrompt({
  target,
  companyName,
  onYes,
  onNo,
}: {
  target: BriefTarget;
  companyName: string | null;
  onYes: () => Promise<void>;
  onNo: () => void;
}) {
  const [working, setWorking] = useState(false);

  async function yes() {
    setWorking(true);
    try {
      await onYes();
    } finally {
      setWorking(false);
    }
  }

  return (
    <div
      role="group"
      aria-label="Research the chosen offering"
      className="mb-4 flex flex-wrap items-center justify-between gap-3 border border-primary bg-card p-4"
    >
      <p className="min-w-0 flex-1 text-sm">
        <span className="font-bold">Search for {target.name}?</span>{" "}
        <span className="text-muted-foreground">
          This opens a separate brief for {companyName ?? "this company"} called
          &ldquo;{titleCaseArea(target.areaLabel)}&rdquo;: what they are doing
          there, how {target.name} fits and who to talk to. You can switch
          between briefs above.
        </span>
      </p>
      <div className="flex gap-2">
        <Button
          type="button"
          className="text-sm font-semibold"
          disabled={working}
          onClick={yes}
        >
          {working ? "Opening…" : "Yes, search"}
        </Button>
        <Button
          type="button"
          variant="action"
          disabled={working}
          onClick={onNo}
        >
          Not now
        </Button>
      </div>
    </div>
  );
}
