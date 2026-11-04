import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CriteriaPicker } from "@/features/quicklook/CriteriaPicker";
import type { Extras } from "@/features/quicklook/extras";

// Optional extras for a look-up. Nothing here is required, and nothing is used unless chosen:
// criteria are typed here. They are checked for information only, they never block
// the look-up or change the call.
export function AdvancedOptions({
  extras,
  onChange,
}: {
  extras: Extras;
  onChange: (next: Extras) => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="lookup-focus">Area to research (optional)</Label>
        <Input
          id="lookup-focus"
          value={extras.focus}
          onChange={(e) => onChange({ ...extras, focus: e.target.value })}
          placeholder="e.g. cloud migration, or a technology or service line"
          maxLength={200}
        />
        <p className="text-xs text-muted-foreground">
          The look-up also searches for what this company is doing in that area
          and says what it found.
        </p>
      </div>

      <CriteriaPicker extras={extras} onChange={onChange} />
    </div>
  );
}
