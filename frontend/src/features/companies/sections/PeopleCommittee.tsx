import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type { CompanyOpportunity } from "@/api/types";
import { SimpleSelect } from "@/components/SimpleSelect";
import { Button } from "@/components/ui/button";
import { AddPerson } from "@/features/brief/AddPerson";
import { titleCaseArea } from "@/features/brief/startBrief";
import { tierPeople } from "@/features/brief/tiers";
import { useBriefDetail } from "@/features/brief/useBriefDetail";
import { useBriefFilter } from "@/features/brief/useBriefFilter";
import { useOfferingOptions } from "@/features/brief/useOfferingOptions";
import { useOpportunities } from "@/features/brief/useOpportunities";
import {
  committeeFrom,
  type CommitteeData,
} from "@/features/companies/lib/committee";

// What the People tab's header shows next to its own buttons: the person-related actions and
// any notes about them. Kept as pieces so the header stays one row of buttons.
export type PeopleTools = {
  actions: ReactNode;
  notes: ReactNode;
};

// The area whose people are ranked: the one named in the address, otherwise the first area that
// has been researched (people are judged against an area and an offering, so an area is needed).
export function pickCommitteeArea(
  items: CompanyOpportunity[],
  areaParam: string | null,
): CompanyOpportunity | null {
  const researched = items.filter(
    (o) => o.area_key !== "general" && o.assessment !== null,
  );
  return researched.find((o) => o.id === areaParam) ?? researched[0] ?? null;
}

function Ranked({
  opportunity,
  researched,
  offeringIds,
  onChanged,
  onPickArea,
  children,
}: {
  opportunity: CompanyOpportunity;
  researched: CompanyOpportunity[];
  offeringIds: string[];
  onChanged: () => void;
  onPickArea: (id: string) => void;
  children: (committee: CommitteeData | null, tools: PeopleTools) => ReactNode;
}) {
  const detail = useBriefDetail(
    opportunity.id,
    offeringIds,
    onChanged,
    "No offering could be matched to this area yet, so no roles were suggested. Work out the best offering on the Brief tab first.",
  );
  const contacts = detail.contacts ?? [];
  const working = detail.busy === "analyse";
  const tools: PeopleTools = {
    actions: (
      <>
        {researched.length > 1 && (
          <SimpleSelect
            label="Area to suggest roles for"
            value={opportunity.id}
            options={researched.map((o) => ({
              value: o.id,
              label: titleCaseArea(o.area_label),
            }))}
            onChange={onPickArea}
            className="w-44"
          />
        )}
        <Button
          type="button"
          variant="action"
          disabled={working}
          onClick={() => detail.analyse(false)}
        >
          {working
            ? "Working…"
            : detail.focus
              ? "Suggest roles again"
              : "Suggest buying roles"}
        </Button>
        <AddPerson
          companyId={opportunity.company_id}
          onAdded={async () => {
            await detail.analyse(false);
          }}
        />
      </>
    ),
    notes: (
      <>
        {detail.error && (
          <p role="alert" className="text-sm text-destructive">
            {detail.error}
          </p>
        )}
        {detail.notice && (
          <p role="status" className="text-sm text-muted-foreground">
            {detail.notice}{" "}
            <Link
              to={`/companies/${opportunity.company_id}?tab=opportunity&area=${opportunity.id}`}
              className="font-medium text-primary-text hover:underline"
            >
              Open the Brief
            </Link>
          </p>
        )}
        {opportunity.research?.people?.summary && (
          <p className="text-xs text-muted-foreground">
            {opportunity.research.people.summary}
          </p>
        )}
      </>
    ),
  };
  return (
    <>
      {children(
        committeeFrom(contacts, tierPeople(contacts), detail.override),
        tools,
      )}
    </>
  );
}

// Ranking people by their part in the buying decision, offered as two buttons in the People
// header rather than a panel of its own. The result goes to the one list of people, where each
// person shows their part in front of their name and can change it.
export function PeopleCommittee({
  companyId,
  onChanged,
  children,
}: {
  companyId: string;
  onChanged: () => void;
  children: (committee: CommitteeData | null, tools: PeopleTools) => ReactNode;
}) {
  const opps = useOpportunities(companyId);
  const offerings = useOfferingOptions();
  const filter = useBriefFilter([], offerings.known);
  const [params, setParams] = useSearchParams();

  const addOnly = (
    <AddPerson companyId={companyId} onAdded={async () => onChanged()} />
  );

  if (opps.items === null) {
    return <>{children(null, { actions: addOnly, notes: null })}</>;
  }
  const area = pickCommitteeArea(opps.items, params.get("area"));
  const researched = opps.items.filter(
    (o) => o.area_key !== "general" && o.assessment !== null,
  );

  if (!area) {
    return (
      <>
        {children(null, {
          actions: addOnly,
          notes: (
            <p className="text-sm text-muted-foreground">
              Want to know who would decide, influence or use an offering?{" "}
              <Link
                to={`/companies/${companyId}?tab=opportunity`}
                className="font-medium text-primary-text hover:underline"
              >
                Create a brief
              </Link>{" "}
              first and the people can be sorted for it.
            </p>
          ),
        })}
      </>
    );
  }

  return (
    <Ranked
      key={area.id}
      opportunity={area}
      researched={researched}
      offeringIds={filter.offeringIds}
      onChanged={onChanged}
      onPickArea={(id) =>
        setParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            next.set("area", id);
            return next;
          },
          { replace: true },
        )
      }
    >
      {children}
    </Ranked>
  );
}
