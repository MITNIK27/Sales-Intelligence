import { AlertTriangle, Compass, FileText, Send } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

import type { DashboardActivityEvent } from "@/api/types";
import { SkeletonLines } from "@/components/Skeleton";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const SHOWN = 5;

const ICONS: Record<
  DashboardActivityEvent["kind"],
  { icon: LucideIcon; cls: string }
> = {
  search: { icon: Compass, cls: "text-primary-text" },
  draft: { icon: FileText, cls: "text-foreground" },
  outreach: { icon: Send, cls: "text-success" },
  failure: { icon: AlertTriangle, cls: "text-destructive" },
};

// Where a click on an event should lead: a search to its results, a draft to the Drafts page, a
// company to its page.
function target(event: DashboardActivityEvent): string | null {
  if (event.kind === "draft") return "/drafts";
  if (event.run_id) return `/?search=${event.run_id}`;
  if (event.company_id) return `/companies/${event.company_id}`;
  return null;
}

export function ActivityFeed({
  events,
}: {
  events: DashboardActivityEvent[] | null;
}) {
  if (events === null) return <SkeletonLines lines={4} />;
  if (events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing yet. Searches, drafts and messages appear here as they happen.
      </p>
    );
  }
  return (
    <ol className="flex flex-col">
      {events.slice(0, SHOWN).map((event, index) => {
        const { icon: Icon, cls } = ICONS[event.kind];
        const href = target(event);
        const row = (
          <div
            className={cn(
              "flex items-center gap-3 py-2",
              href && "transition-colors duration-200 hover:bg-muted/60",
            )}
            title={event.text}
          >
            <Icon className={cn("size-4 shrink-0", cls)} aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate text-sm">
              {event.text}
            </span>
            <time
              dateTime={event.at}
              className="shrink-0 text-xs text-muted-foreground"
            >
              {timeAgo(event.at)}
            </time>
          </div>
        );
        return (
          <li
            key={`${event.at}-${index}`}
            className="border-b border-border last:border-b-0"
          >
            {href ? (
              <Link
                to={href}
                className="block focus-visible:outline-2 focus-visible:outline-primary"
              >
                {row}
              </Link>
            ) : (
              row
            )}
          </li>
        );
      })}
    </ol>
  );
}
