import type { CompanyOpportunity } from "@/api/types";
import { SimpleSelect } from "@/components/SimpleSelect";
import { Button } from "@/components/ui/button";

// Three plain ways to look elsewhere (another area, the company overall, other suggested areas).
// They only change what the brief is about; nothing is researched until a person asks for it.
// Another offering is chosen with Our offerings above.
export function AngleBody({
  areas,
  areaId,
  suggesting,
  onPickArea,
  onOverall,
  onSuggest,
}: {
  areas: CompanyOpportunity[];
  areaId: string | null;
  suggesting: boolean;
  onPickArea: (id: string) => void;
  onOverall: () => void;
  onSuggest: () => void;
}) {
  const others = areas.filter(
    (a) => a.id !== areaId && a.area_key !== "general",
  );
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        This brief covers one area and one offering. Choose another offering
        with Our offerings above, or:
      </p>
      <div className="flex flex-wrap items-center gap-3">
        {others.length > 0 && (
          <SimpleSelect
            label="Switch area"
            placeholder="Switch to another area"
            value=""
            options={others.map((a) => ({ value: a.id, label: a.area_label }))}
            onChange={onPickArea}
            className="w-56"
          />
        )}
        <Button variant="outline" onClick={onOverall}>
          Look at the company as a whole
        </Button>
        <Button variant="outline" disabled={suggesting} onClick={onSuggest}>
          {suggesting ? "Looking…" : "Suggest other areas"}
        </Button>
      </div>
    </div>
  );
}
