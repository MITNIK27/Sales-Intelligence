import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export type SegmentOption<T extends string> = {
  id: T;
  label: string;
  // Shown after the label, for example "suggested".
  hint?: string;
};

// A pick-one control for a few choices. Every choice is a bordered button in one joined row, the
// chosen one is filled and carries a check (so it does not rely on colour), and the group is
// announced as one set of radio-like choices. Use it where the options are few and mutually
// exclusive; use a dropdown for many.
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: SegmentOption<T>[];
  value: T | null;
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex flex-wrap border border-border bg-card"
    >
      {options.map((option, i) => {
        const on = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(option.id)}
            className={cn(
              "inline-flex h-9 items-center gap-1.5 px-3 text-sm transition-colors",
              "focus-visible:z-10 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary",
              i > 0 && "border-l border-border",
              on
                ? "bg-primary font-medium text-primary-foreground"
                : "text-foreground hover:bg-muted",
            )}
          >
            {on && <Check className="size-3.5" aria-hidden="true" />}
            {option.label}
            {option.hint && (
              <span
                className={cn(
                  "text-xs",
                  on ? "text-primary-foreground/80" : "text-muted-foreground",
                )}
              >
                {option.hint}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
