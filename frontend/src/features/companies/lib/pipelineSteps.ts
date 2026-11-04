import type { QualificationResult } from "@/api/types";
import type { PipelineStep } from "@/components/PipelineStatusStepper";

export type PipelineInput = {
  enrichmentStatus: string;
  enrichmentError: string | null;
  contactCount: number;
  latestQualification: QualificationResult | null;
  rolesClassifiedCount: number;
  draftsGeneratedCount: number;
};

function enrichedStep(input: PipelineInput): PipelineStep {
  const { enrichmentStatus: status } = input;
  if (status === "enriched") {
    return {
      label: "Enriched",
      status: "done",
      detail: "Website scraped for details, signals, and contacts",
    };
  }
  if (status === "pending") {
    return {
      label: "Enriched",
      status: "in_progress",
      detail: "Scraping now…",
    };
  }
  if (status === "failed") {
    return {
      label: "Enriched",
      status: "attention",
      detail: input.enrichmentError ?? "Scrape failed",
    };
  }
  return { label: "Enriched", status: "pending", detail: "Not scraped yet" };
}

// The five steps shown at the top of a company page, from what has actually happened to it.
export function buildPipelineSteps(input: PipelineInput): PipelineStep[] {
  const { latestQualification, rolesClassifiedCount, draftsGeneratedCount } =
    input;
  return [
    { label: "Discovered", status: "done" },
    enrichedStep(input),
    {
      label: "Qualified",
      status:
        latestQualification &&
        latestQualification.overall_verdict !== "not_checked"
          ? "done"
          : "pending",
      detail: !latestQualification
        ? "Not checked yet"
        : latestQualification.overall_verdict === "not_checked"
          ? "Not decided: no criteria were chosen to qualify against"
          : `Verdict: ${latestQualification.overall_verdict.replace(/_/g, " ")}`,
    },
    {
      label: "Roles classified",
      status: rolesClassifiedCount > 0 ? "done" : "pending",
      detail:
        rolesClassifiedCount > 0
          ? `${rolesClassifiedCount} contact(s) classified`
          : input.contactCount === 0
            ? "No contacts yet to classify"
            : "Not classified yet",
    },
    {
      label: "Drafted",
      status: draftsGeneratedCount > 0 ? "done" : "pending",
      detail:
        draftsGeneratedCount > 0
          ? `${draftsGeneratedCount} draft(s) generated`
          : "No drafts generated yet",
    },
  ];
}
