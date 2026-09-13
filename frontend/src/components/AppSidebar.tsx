import {
  ClipboardCheck,
  Compass,
  LayoutDashboard,
  ListChecks,
  Package,
  Search,
  Target,
  Upload,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import { apiGet } from "@/api/client";
import type { FollowUpItem } from "@/api/types";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/upload", label: "Upload", icon: Upload },
  { to: "/companies", label: "Companies", icon: Users },
  { to: "/follow-ups", label: "Follow-ups", icon: ListChecks },
  { to: "/needs-review", label: "Needs Review", icon: Search },
  { to: "/market-discovery", label: "Market Discovery", icon: Compass },
  { to: "/products", label: "Products", icon: Package },
  { to: "/qualification/criteria", label: "Qualification Criteria", icon: ClipboardCheck },
  { to: "/qualification/check", label: "Quick Check", icon: Zap },
  { to: "/role-categories", label: "Role Categories", icon: Target },
];

export function AppSidebar() {
  // Proactive reminder surfacing (Phase C) — a due-count badge on Follow-ups so a rep sees there's
  // something to act on without having to think to click in and check.
  const [dueFollowUpCount, setDueFollowUpCount] = useState<number | null>(null);

  useEffect(() => {
    apiGet<FollowUpItem[]>("/contacts/follow-ups")
      .then((items) => setDueFollowUpCount(items.length))
      .catch(() => {
        // Supplementary — a failure here shouldn't affect the rest of the nav.
      });
  }, []);

  return (
    <aside className="row-span-2 flex h-full w-62 flex-col overflow-hidden bg-sidebar text-sidebar-foreground">
      <Link to="/" className="flex h-15 shrink-0 items-center px-6">
        <Logo on="dark" className="h-10" />
      </Link>
      <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        <h4 className="px-3 py-2 text-xs font-medium uppercase tracking-[0.12em] text-white/45">
          Sales Intelligence
        </h4>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex w-full items-center gap-3 px-4 py-3 text-base text-white/80 transition-colors duration-200",
                "hover:bg-white/6 hover:text-white",
                // selection = crimson tint, NO indicator bar
                isActive && "bg-primary/25 text-white font-semibold",
              )
            }
          >
            <item.icon className="size-4 opacity-85" />
            <span className="flex-1">{item.label}</span>
            {item.to === "/follow-ups" && !!dueFollowUpCount && (
              <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground">
                {dueFollowUpCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
