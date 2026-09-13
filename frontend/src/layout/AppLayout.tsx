import { Outlet } from "react-router-dom";

import { AppFooter } from "@/components/AppFooter";
import { AppSidebar } from "@/components/AppSidebar";
import { Topbar } from "@/components/Topbar";

export function AppLayout() {
  return (
    <div className="grid h-screen grid-cols-[248px_1fr] grid-rows-[60px_1fr] overflow-hidden bg-background">
      <AppSidebar />
      <Topbar />
      <div className="col-start-2 row-start-2 flex min-h-0 flex-col overflow-y-auto">
        <main className="mx-auto w-full max-w-[1320px] flex-1 p-8">
          <Outlet />
        </main>
        <AppFooter />
      </div>
    </div>
  );
}
