import {
  Compass,
  FileText,
  LayoutDashboard,
  Package,
  Send,
  Target,
  Upload,
  UserCog,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { ACTIONS } from "@/auth/types";
import { OFFERINGS_LABEL } from "@/lib/offerings";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  // Shown only to roles allowed this action (Phase 9); no action means everyone signed in.
  action?: string;
}

// Grouped by how the product is used: the daily workflow first, then one-time setup, then tools.
// The sidebar renders this list.
export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Workspace",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
      { to: "/market-discovery", label: "Market Discovery", icon: Compass },
      { to: "/qualification/check", label: "Quick Check", icon: Zap },
      { to: "/companies", label: "Companies", icon: Users },
      { to: "/outreach", label: "Outreach", icon: Send },
    ],
  },
  {
    label: "Configure",
    items: [
      { to: "/products", label: OFFERINGS_LABEL, icon: Package },
      { to: "/role-categories", label: "Role Categories", icon: Target },
      { to: "/documents", label: "Documents", icon: FileText },
      {
        to: "/users",
        label: "User Management",
        icon: UserCog,
        action: ACTIONS.usersManage,
      },
    ],
  },
  {
    label: "Tools",
    items: [{ to: "/upload", label: "Upload CSV", icon: Upload }],
  },
];
