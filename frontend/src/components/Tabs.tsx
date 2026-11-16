import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type TabItem<T extends string> = { id: T; label: string };

// A plain tab bar for switching between parts of one page. The caller decides what each tab
// shows; this only draws the bar and reports the choice.
export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
  trailing,
}: {
  tabs: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
  label: string;
  // Plain information shown at the right end of the bar, for example a fact about the page's subject.
  trailing?: ReactNode;
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="mb-6 flex flex-wrap gap-x-1 border-b border-border"
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={tab.id === active}
          onClick={() => onChange(tab.id)}
          className={cn(
            "-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium transition-colors",
            tab.id === active
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
        </button>
      ))}
      {trailing && (
        <span className="ml-auto self-center pl-4 text-sm text-muted-foreground">
          {trailing}
        </span>
      )}
    </div>
  );
}
