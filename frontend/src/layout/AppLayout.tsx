import { Outlet } from "react-router-dom";

import { AppFooter } from "@/components/AppFooter";
import { AppSidebar } from "@/components/AppSidebar";
import { Topbar } from "@/components/Topbar";
import { usePersistentState } from "@/lib/usePersistentState";

const SIDEBAR_WIDTH = 248;
const SIDEBAR_WIDTH_COLLAPSED = 64;

export function AppLayout() {
  // Remembered across pages and refreshes, so a rep who prefers more room keeps it.
  const [collapsed, setCollapsed] = usePersistentState(
    "ui.sidebarCollapsed",
    false,
  );
  return (
    <div
      // `relative` makes this the containing block for absolutely positioned content (such as
      // screen-reader-only text), so nothing can escape and make the browser window scroll as well.
      className="relative grid h-screen grid-rows-[60px_1fr] overflow-hidden bg-background transition-[grid-template-columns] duration-200 motion-reduce:transition-none"
      style={{
        gridTemplateColumns: `${collapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH}px 1fr`,
      }}
    >
      <AppSidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed(!collapsed)}
      />
      <Topbar />
      <div className="relative col-start-2 row-start-2 flex min-h-0 flex-col overflow-y-auto">
        <main className="mx-auto w-full max-w-[1760px] flex-1 px-8 py-6">
          <Outlet />
        </main>
        <AppFooter />
      </div>
    </div>
  );
}
