import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Collapsible } from "radix-ui";

// One collapsible section of the Brief, drawn as a solid white card on the cream page: a crimson
// number tile, the title and a one-line summary, and a round chevron. It has a coloured edge and a
// tinted header when open, so open and closed sections are easy to tell apart. An action (a
// button) sits beside the title and works without opening the section.
export function BriefSection({
  number,
  title,
  summary,
  action,
  defaultOpen = false,
  children,
}: {
  number: number;
  title: string;
  summary?: string;
  action?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <Collapsible.Root
      defaultOpen={defaultOpen}
      className="group/section mb-4 overflow-hidden rounded-xl border-l-4 border-l-border bg-card shadow-sm ring-1 ring-foreground/15 transition-shadow data-[state=open]:border-l-primary data-[state=open]:shadow-md"
    >
      <div className="flex flex-wrap items-center gap-2 bg-card pr-3 transition-colors group-data-[state=open]/section:bg-secondary sm:flex-nowrap">
        <h2 className="min-w-0 flex-1">
          <Collapsible.Trigger className="group flex w-full items-center gap-4 px-4 py-4 text-left transition-colors hover:bg-secondary/70 focus-visible:ring-3 focus-visible:ring-ring/50">
            <span
              aria-hidden="true"
              className="grid size-8 shrink-0 place-items-center bg-primary text-sm font-bold text-primary-foreground"
            >
              {number}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-lg font-bold">{title}</span>
              {summary && (
                <span className="block break-words text-sm font-normal text-muted-foreground">
                  {summary}
                </span>
              )}
            </span>
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-card ring-1 ring-foreground/20">
              <ChevronDown
                className="size-4 transition-transform group-data-[state=open]:rotate-180"
                aria-hidden="true"
              />
            </span>
          </Collapsible.Trigger>
        </h2>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      <Collapsible.Content className="border-t border-foreground/10 bg-card px-5 py-5 data-[state=open]:animate-in data-[state=open]:fade-in-0">
        {children}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
