import { Link } from "react-router-dom";

import type { ContactRelevance } from "@/api/types";
import { ROLE_LABEL } from "@/features/brief/opportunityLabels";

// Who to approach first, in one line. The full buying committee (everyone's part in the decision,
// and the way to change it) lives on the People tab, where people are managed.
export function StartWith({
  lead,
  peopleKnown,
  companyId,
}: {
  lead: ContactRelevance | null;
  peopleKnown: number;
  companyId: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      {lead ? (
        <p className="text-base">
          Start with{" "}
          <span className="font-bold">
            {lead.full_name ?? "the top contact"}
          </span>
          {lead.role_title ? `, ${lead.role_title}` : ""}
          {lead.role ? ` (${ROLE_LABEL[lead.role]})` : ""}.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          {peopleKnown} {peopleKnown === 1 ? "person is" : "people are"} known,
          but nobody has been matched to the decision yet.
        </p>
      )}
      {lead?.reasoning && (
        <p className="text-sm text-muted-foreground">{lead.reasoning}</p>
      )}
      <Link
        to={`/companies/${companyId}?tab=people`}
        className="text-sm font-medium text-primary-text underline-offset-4 hover:underline"
      >
        See everyone on the People tab
      </Link>
    </div>
  );
}
