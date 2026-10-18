import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import { apiGet } from "@/api/client";
import type { FollowUpItem } from "@/api/types";
import { Logo } from "@/components/Logo";
import { APP_VERSION } from "@/lib/app-meta";
import { NAV_GROUPS } from "@/lib/nav";
import { cn } from "@/lib/utils";

export function AppSidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  // Proactive reminder surfacing (Phase C) — a due-count badge on Follow-ups so a rep sees there's
  // something to act on without having to think to click in and check.
  const [dueFollowUpCount, setDueFollowUpCount] = useState<number | null>(null);
  const [draftsToReview, setDraftsToReview] = useState<number | null>(null);

  useEffect(() => {
    apiGet<FollowUpItem[]>("/contacts/follow-ups")
      .then((items) => setDueFollowUpCount(items.length))
      .catch(() => {
        // Supplementary — a failure here shouldn't affect the rest of the nav.
      });
    apiGet<{ counts: { draft: number } }>("/drafts?status=draft&limit=1")
      .then((list) => setDraftsToReview(list.counts.draft))
      .catch(() => {
        // Supplementary — a failure here shouldn't affect the rest of the nav.
      });
  }, []);

  const badgeFor = (to: string): number | null => {
    if (to === "/drafts") return draftsToReview;
    if (to === "/follow-ups") return dueFollowUpCount;
    return null;
  };

  return (
    <aside
      className="row-span-2 flex h-full flex-col overflow-hidden bg-sidebar text-sidebar-foreground"
      aria-label="Main navigation"
    >
      <div
        className={cn(
          "flex h-15 shrink-0 items-center",
          collapsed ? "justify-center" : "justify-between pl-6 pr-3",
        )}
      >
        {!collapsed && (
          <Link to="/" aria-label="Sales Intelligence home">
            <Logo on="dark" className="h-10" />
          </Link>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
          title={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
          className="grid size-9 place-items-center text-white/70 transition-colors duration-200 hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-primary"
        >
          {collapsed ? (
            <PanelLeftOpen className="size-5" />
          ) : (
            <PanelLeftClose className="size-5" />
          )}
        </button>
      </div>
      <nav
        className={cn(
          "min-h-0 flex-1 overflow-y-auto pb-4 pt-2",
          collapsed ? "px-2" : "px-3",
        )}
      >
        {NAV_GROUPS.map((group, groupIndex) => (
          <div key={group.label} className={cn(groupIndex > 0 && "mt-4")}>
            {collapsed ? (
              groupIndex > 0 && (
                <div
                  className="mx-3 mb-2 border-t border-white/10"
                  aria-hidden="true"
                />
              )
            ) : (
              <h4 className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/40">
                {group.label}
              </h4>
            )}
            {group.items.map((item) => {
              const badge = badgeFor(item.to);
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  title={collapsed ? item.label : undefined}
                  aria-label={collapsed ? item.label : undefined}
                  className={({ isActive }) =>
                    cn(
                      "relative flex w-full items-center text-sm text-white/75 transition-colors duration-200",
                      collapsed
                        ? "justify-center px-0 py-2.5"
                        : "gap-3 px-3 py-2.5",
                      "hover:bg-white/8 hover:text-white",
                      // selection = crimson tint, NO indicator bar
                      isActive && "bg-primary/25 font-semibold text-white",
                    )
                  }
                >
                  <item.icon
                    className={cn(
                      "shrink-0 opacity-85",
                      collapsed ? "size-5" : "size-4",
                    )}
                  />
                  {!collapsed && (
                    <span className="flex-1 truncate">{item.label}</span>
                  )}
                  {!!badge && (
                    <span
                      className={cn(
                        "flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground",
                        collapsed &&
                          "absolute right-1 top-0.5 h-4 min-w-4 px-1 text-[10px]",
                      )}
                      aria-label={`${badge} waiting`}
                    >
                      {badge}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>
      {!collapsed && (
        <p className="shrink-0 border-t border-white/10 px-6 py-3 text-[11px] text-white/40">
          Sales Intelligence · v{APP_VERSION}
        </p>
      )}
    </aside>
  );
}
