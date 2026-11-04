import { Info } from "lucide-react";

import type { QualificationResult } from "@/api/types";
import {
  CriterionVerdictBadge,
  QualificationVerdictBadge,
} from "@/components/StatusBadge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatDateTime } from "@/lib/format";

/** Renders a list of qualification results (newest typically first) as a compact table — one
 * row per check, one chip per criterion. Shared between CompanyDetailPage's history view and the
 * ad hoc quick-check page, which shows a single freshly-created result in the same shape. */
export function QualificationResultsTable({
  results,
}: {
  results: QualificationResult[];
}) {
  return (
    <TooltipProvider>
      <Card className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Checked</TableHead>
              <TableHead>Overall</TableHead>
              <TableHead>
                <span className="inline-flex items-center gap-1">
                  Criteria
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-foreground"
                        aria-label="How to read this column"
                      >
                        <Info className="size-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent className="block max-w-xs whitespace-normal text-left">
                      <ul className="list-disc space-y-0.5 pl-3.5">
                        <li>Hover a chip to see its reasoning.</li>
                        <li>
                          * marks a must-have for that search; only must-haves
                          can rule a company out.
                        </li>
                      </ul>
                    </TooltipContent>
                  </Tooltip>
                </span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((result) => (
              <TableRow key={result.id}>
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {formatDateTime(result.created_at)}
                </TableCell>
                <TableCell>
                  {result.overall_verdict === "not_checked" ? (
                    <span className="text-sm text-muted-foreground">
                      {result.criteria_results.length > 0
                        ? "For information"
                        : "No criteria chosen"}
                    </span>
                  ) : (
                    <QualificationVerdictBadge
                      verdict={result.overall_verdict}
                    />
                  )}
                </TableCell>
                <TableCell className="whitespace-normal">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {result.criteria_results.map((entry) => (
                      <Tooltip key={entry.criterion_id}>
                        <TooltipTrigger className="cursor-default">
                          <CriterionVerdictBadge
                            verdict={entry.verdict}
                            label={
                              entry.criterion_name +
                              (entry.is_disqualifying ? " *" : "")
                            }
                          />
                        </TooltipTrigger>
                        <TooltipContent className="block max-w-sm whitespace-normal text-left">
                          {entry.reasoning}
                        </TooltipContent>
                      </Tooltip>
                    ))}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </TooltipProvider>
  );
}
