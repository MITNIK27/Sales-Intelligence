import type { CompanyDetail } from "@/api/types";
import { WebsiteLink } from "@/components/WebsiteLink";
import { Card, CardContent } from "@/components/ui/card";

export function CompanyOverview({ company }: { company: CompanyDetail }) {
  return (
    <Card>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Website</dt>
          <dd>
            {company.domain ? <WebsiteLink domain={company.domain} /> : "—"}
          </dd>
          <dt className="text-muted-foreground">Industry</dt>
          <dd>{company.industry ?? "—"}</dd>
          <dt className="text-muted-foreground">Employee count</dt>
          <dd>{company.employee_count_range ?? "—"}</dd>
          {company.description && (
            <>
              <dt className="text-muted-foreground">Description</dt>
              <dd>{company.description}</dd>
            </>
          )}
        </dl>
      </CardContent>
    </Card>
  );
}
