import { useState } from "react";

import type { OfferingFit } from "@/api/types";
import { SimpleSelect } from "@/components/SimpleSelect";
import { BAND_LABEL } from "@/features/brief/opportunityLabels";

const Pick = ({
  label,
  value,
  fit,
  onChange,
}: {
  label: string;
  value: string;
  fit: OfferingFit[];
  onChange: (id: string) => void;
}) => (
  <SimpleSelect
    label={label}
    value={value}
    onChange={onChange}
    className="w-full"
    options={fit.map((f) => ({ value: f.product_id, label: f.product_name }))}
  />
);

function Side({ item }: { item: OfferingFit }) {
  return (
    <div className="text-sm">
      <p className="font-medium">
        {BAND_LABEL[item.band]}
        {item.needs_review ? " · please check" : ""}
      </p>
      <p className="mt-1 text-muted-foreground">{item.reasoning}</p>
      <p className="mt-2 text-xs text-muted-foreground">
        {item.factors.verified_evidence} verified citation
        {item.factors.verified_evidence === 1 ? "" : "s"} ·{" "}
        {item.factors.area_alignment
          ? "belongs to this area"
          : "not tied to this area"}
      </p>
      {item.evidence.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">
          No supporting evidence was verified.
        </p>
      ) : (
        <ul className="mt-1 flex flex-col gap-0.5 text-xs text-muted-foreground">
          {item.evidence.map((e, i) => (
            <li key={i}>“{e.quote}”</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Two offerings side by side for the same company and area, so a rep can see which is better
// supported and why. Nothing here is recomputed; it reads the stored judgments.
export function CompareOfferings({ fit }: { fit: OfferingFit[] }) {
  const [a, setA] = useState(fit[0].product_id);
  const [b, setB] = useState(fit[1].product_id);
  const left = fit.find((f) => f.product_id === a) ?? fit[0];
  const right = fit.find((f) => f.product_id === b) ?? fit[1];
  return (
    <div className="mt-3 grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-2">
        <Pick label="First offering" value={a} fit={fit} onChange={setA} />
        <Side item={left} />
      </div>
      <div className="flex flex-col gap-2">
        <Pick label="Second offering" value={b} fit={fit} onChange={setB} />
        <Side item={right} />
      </div>
    </div>
  );
}
