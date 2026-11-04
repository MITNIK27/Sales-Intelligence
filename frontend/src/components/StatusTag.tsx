import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type Tone = "good" | "watch" | "neutral" | "bad";

const DOT: Record<Tone, string> = {
  good: "bg-chip-success-fg",
  watch: "bg-chip-warning-fg",
  neutral: "bg-muted-foreground",
  bad: "bg-chip-rejected-fg",
};

const TEXT: Record<Tone, string> = {
  good: "text-chip-success-fg",
  watch: "text-chip-warning-fg",
  neutral: "text-muted-foreground",
  bad: "text-chip-rejected-fg",
};

// A status is read, not pressed: a dot and a word, no border and no fill, so it can never be
// mistaken for a button. Meaning is in the word; the dot only reinforces it.
export function StatusTag({
  tone,
  children,
  className,
}: {
  tone: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-sm font-medium",
        TEXT[tone],
        className,
      )}
    >
      <span
        className={cn("size-2 shrink-0 rounded-full", DOT[tone])}
        aria-hidden="true"
      />
      {children}
    </span>
  );
}
