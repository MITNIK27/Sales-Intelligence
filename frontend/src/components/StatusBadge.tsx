import type { EnrichmentStatus, QualificationVerdict, RolePriority } from "@/api/types";
import { cn } from "@/lib/utils";

const ENRICHMENT_MAP: Record<EnrichmentStatus, { label: string; cls: string }> = {
  never_enriched: { label: "Not enriched", cls: "bg-muted text-muted-foreground" },
  pending: { label: "Enriching…", cls: "bg-chip-warning-bg text-chip-warning-fg" },
  enriched: { label: "Enriched", cls: "bg-chip-success-bg text-chip-success-fg" },
  failed: { label: "Failed", cls: "bg-chip-rejected-bg text-chip-rejected-fg" },
};

const QUALIFICATION_VERDICT_MAP: Record<QualificationVerdict, { label: string; cls: string }> = {
  qualified: { label: "Qualified", cls: "bg-chip-success-bg text-chip-success-fg" },
  not_qualified: { label: "Not qualified", cls: "bg-chip-rejected-bg text-chip-rejected-fg" },
  could_not_determine: {
    label: "Could not determine",
    cls: "bg-chip-warning-bg text-chip-warning-fg",
  },
};

const CRITERION_VERDICT_MAP: Record<
  "met" | "not_met" | "could_not_determine",
  { label: string; cls: string }
> = {
  met: { label: "Met", cls: "bg-chip-success-bg text-chip-success-fg" },
  not_met: { label: "Not met", cls: "bg-chip-rejected-bg text-chip-rejected-fg" },
  could_not_determine: {
    label: "Could not determine",
    cls: "bg-chip-warning-bg text-chip-warning-fg",
  },
};

const ROLE_PRIORITY_MAP: Record<RolePriority, { label: string; cls: string }> = {
  primary: { label: "Primary target", cls: "bg-chip-success-bg text-chip-success-fg" },
  secondary: { label: "Secondary", cls: "bg-muted text-muted-foreground" },
  not_relevant: { label: "Not relevant", cls: "bg-chip-rejected-bg text-chip-rejected-fg" },
};

function Chip({ label, cls }: { label: string; cls: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold uppercase tracking-wide",
        cls,
      )}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

export function EnrichmentStatusBadge({ status }: { status: EnrichmentStatus }) {
  const { label, cls } = ENRICHMENT_MAP[status];
  return <Chip label={label} cls={cls} />;
}

export function NeedsReviewBadge({ reason }: { reason?: string | null }) {
  return (
    <span title={reason ?? undefined}>
      <Chip label="Needs review" cls="bg-chip-warning-bg text-chip-warning-fg" />
    </span>
  );
}

/** Flags a parsed field the model could not confidently determine. */
export function CouldNotDetermineBadge() {
  return <Chip label="Could not determine" cls="bg-chip-warning-bg text-chip-warning-fg" />;
}

/** Generic signal-type chip used on the company detail page. */
export function SignalTypeBadge({ type }: { type: "news" | "job_posting" }) {
  return type === "news" ? (
    <Chip label="News" cls="bg-muted text-muted-foreground" />
  ) : (
    <Chip label="Hiring" cls="bg-chip-warning-bg text-chip-warning-fg" />
  );
}

export function QualificationVerdictBadge({ verdict }: { verdict: QualificationVerdict }) {
  const { label, cls } = QUALIFICATION_VERDICT_MAP[verdict];
  return <Chip label={label} cls={cls} />;
}

/** Smaller per-criterion verdict indicator shown in a qualification result's breakdown — color
 * communicates the verdict, `label` (typically the criterion name) is shown as the text so a
 * row of these reads as "which criteria, and how each landed" at a glance. */
export function CriterionVerdictBadge({
  verdict,
  label,
}: {
  verdict: "met" | "not_met" | "could_not_determine";
  label?: string;
}) {
  const { label: defaultLabel, cls } = CRITERION_VERDICT_MAP[verdict];
  return <Chip label={label ?? defaultLabel} cls={cls} />;
}

/** Per-contact role-relevance indicator — `label` (typically the matched category name, or
 * "No match" when there wasn't one) is shown as the text, color communicates the priority. */
export function RolePriorityBadge({ priority, label }: { priority: RolePriority; label?: string }) {
  const { label: defaultLabel, cls } = ROLE_PRIORITY_MAP[priority];
  return <Chip label={label ?? defaultLabel} cls={cls} />;
}
