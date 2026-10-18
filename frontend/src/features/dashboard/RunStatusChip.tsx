import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

const STATUS: Record<string, { label: string; cls: string }> = {
  done: { label: "Finished", cls: "bg-chip-success-bg text-chip-success-fg" },
  running: { label: "Running", cls: "bg-chip-warning-bg text-chip-warning-fg" },
  pending: { label: "Queued", cls: "bg-chip-warning-bg text-chip-warning-fg" },
  failed: { label: "Failed", cls: "bg-chip-rejected-bg text-chip-rejected-fg" },
};

// Word plus (for in-flight runs) a spinner, never colour alone.
export function RunStatusChip({ status }: { status: string }) {
  const { label, cls } = STATUS[status] ?? {
    label: status,
    cls: "bg-muted text-muted-foreground",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium",
        cls,
      )}
    >
      {(status === "running" || status === "pending") && (
        <Loader2 className="size-3 motion-safe:animate-spin" />
      )}
      {label}
    </span>
  );
}
