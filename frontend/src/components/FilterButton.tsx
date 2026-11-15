import { Check, ChevronDown, X } from "lucide-react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export type FilterOption = { id: string; label: string; group?: string };

// A filter you can see is a control: a bordered button with a label, the current choice and a
// caret. It opens a checklist (several can be chosen), shows a check on each chosen row and a
// clear action. The closed button always says what is applied, so the filter is never invisible.
export function FilterButton({
  label,
  options,
  selected,
  onToggle,
  onClear,
  emptyText,
  note,
  showChoice = true,
}: {
  label: string;
  options: FilterOption[];
  selected: string[];
  onToggle: (id: string) => void;
  onClear: () => void;
  emptyText: string;
  note?: string | null;
  // False when the chosen options are shown elsewhere (as chips): the button then shows a count.
  showChoice?: boolean;
}) {
  const chosen = options.filter((o) => selected.includes(o.id));
  const summary =
    chosen.length === 0
      ? emptyText
      : chosen.length === 1
        ? chosen[0].label
        : `${chosen.length} selected`;
  const groups = [...new Set(options.map((o) => o.group ?? ""))];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`${label}: ${summary}`}
          className={cn(
            "inline-flex h-10 max-w-72 items-center gap-2 border bg-card px-3 text-sm",
            "shadow-xs transition-colors hover:border-primary hover:bg-muted",
            "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary",
            chosen.length > 0 ? "border-primary" : "border-border",
          )}
        >
          <span className="whitespace-nowrap text-muted-foreground">
            {label}
          </span>
          {showChoice ? (
            <span className="truncate font-medium">{summary}</span>
          ) : (
            chosen.length > 0 && (
              <span className="bg-primary px-1.5 text-xs font-bold text-primary-foreground">
                {chosen.length}
              </span>
            )
          )}
          <ChevronDown
            className="size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start">
        <div className="flex max-h-72 flex-col gap-1 overflow-y-auto p-2">
          {groups.map((group) => (
            <div key={group || "all"} className="flex flex-col">
              {group && (
                <p className="px-2 pb-1 pt-2 text-xs font-semibold text-muted-foreground">
                  {group}
                </p>
              )}
              {options
                .filter((o) => (o.group ?? "") === group)
                .map((o) => {
                  const on = selected.includes(o.id);
                  return (
                    <button
                      key={o.id}
                      type="button"
                      role="checkbox"
                      aria-checked={on}
                      onClick={() => onToggle(o.id)}
                      className="flex items-center gap-2 px-2 py-1.5 text-left text-sm hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
                    >
                      <span
                        className={cn(
                          "flex size-4 shrink-0 items-center justify-center border",
                          on
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border",
                        )}
                      >
                        {on && <Check className="size-3" aria-hidden="true" />}
                      </span>
                      {o.label}
                    </button>
                  );
                })}
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted-foreground">
          <span>{note ?? ""}</span>
          {selected.length > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="inline-flex items-center gap-1 text-foreground hover:underline"
            >
              <X className="size-3" aria-hidden="true" /> Clear
            </button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
