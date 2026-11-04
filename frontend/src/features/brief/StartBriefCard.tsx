import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { BriefTarget } from "@/features/brief/startBrief";

// Shown when no brief is open yet. With no offering chosen it explains how to start one; with one
// or more chosen it offers to create a brief around each, so picking an offering leads somewhere
// instead of waiting for an area to be typed.
export function StartBriefCard({
  companyName,
  targets,
  onCreate,
  onOverall,
}: {
  companyName: string | null;
  targets: BriefTarget[];
  onCreate: (areaLabel: string) => Promise<void>;
  onOverall: () => void;
}) {
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState<string | null>(null);
  const company = companyName ?? "this company";

  async function create(target: BriefTarget) {
    const label = (labels[target.id] ?? target.areaLabel).trim();
    if (!label) return;
    setCreating(target.id);
    try {
      await onCreate(label);
    } finally {
      setCreating(null);
    }
  }

  if (targets.length === 0) {
    return (
      <Card>
        <CardContent>
          <h2 className="text-lg font-bold">Start a brief</h2>
          <p className="mb-3 text-sm text-muted-foreground">
            Pick one of our offerings above to create a brief around it, or add
            an area, for example “cloud migration”, to research what {company}{" "}
            is doing there and who to talk to.
          </p>
          <Button variant="outline" onClick={onOverall}>
            Look at the company as a whole
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-5">
        {targets.map((target) => (
          <div key={target.id} className="flex flex-col gap-2">
            <h2 className="text-lg font-bold">
              Create a brief around {target.name}?
            </h2>
            <p className="text-sm text-muted-foreground">
              This researches what {company} is doing in this area, how that
              connects to {target.name}, and who to talk to.
            </p>
            <div className="flex flex-col gap-1.5 sm:max-w-xl">
              <Label htmlFor={`brief-area-${target.id}`}>
                Area to research
              </Label>
              <div className="flex gap-2">
                <Input
                  id={`brief-area-${target.id}`}
                  value={labels[target.id] ?? target.areaLabel}
                  onChange={(e) =>
                    setLabels((prev) => ({
                      ...prev,
                      [target.id]: e.target.value,
                    }))
                  }
                  maxLength={200}
                />
                <Button
                  disabled={creating !== null}
                  onClick={() => void create(target)}
                >
                  {creating === target.id ? "Creating…" : "Create brief"}
                </Button>
              </div>
            </div>
          </div>
        ))}
        <div>
          <Button variant="outline" onClick={onOverall}>
            Look at the company as a whole
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
