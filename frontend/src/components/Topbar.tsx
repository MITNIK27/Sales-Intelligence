import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet } from "@/api/client";
import { Button } from "@/components/ui/button";
import { APP_NAME } from "@/lib/app-meta";

type Health = "checking" | "online" | "offline";

// The product header. Left: the product name and the page you are on, so the title is the same on
// every screen and always says where you are. Right: the one action useful from every page (start
// a new search) and, while developing or if the system cannot be reached, its status. A healthy
// production system shows no status at all.
export function Topbar() {
  const [health, setHealth] = useState<Health>("checking");

  useEffect(() => {
    let alive = true;
    const check = () =>
      apiGet<{ status: string }>("/health")
        .then(
          (r) => alive && setHealth(r.status === "ok" ? "online" : "offline"),
        )
        .catch(() => alive && setHealth("offline"));
    check();
    const timer = window.setInterval(check, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  // Development always shows the status; a deployed build only speaks up when something is wrong.
  const showStatus = import.meta.env.DEV || health === "offline";

  return (
    <header className="col-start-2 row-start-1 flex h-15 items-center justify-between gap-6 border-b-2 border-primary bg-card px-8">
      <p className="min-w-0 truncate text-lg font-bold tracking-tight text-foreground">
        {APP_NAME}
      </p>

      <div className="flex shrink-0 items-center gap-5">
        {showStatus && (
          <div
            className="flex items-center gap-2 text-sm text-muted-foreground"
            role="status"
            aria-live="polite"
          >
            <span
              className={`inline-block size-2.5 rounded-full ${
                health === "online"
                  ? "bg-success"
                  : health === "offline"
                    ? "bg-destructive"
                    : "bg-muted-foreground/50"
              }`}
              aria-hidden="true"
            />
            {health === "online"
              ? "Online"
              : health === "offline"
                ? "Unreachable"
                : "Checking"}
          </div>
        )}
        <Button asChild size="sm">
          <Link to="/market-discovery">
            <Plus className="size-4" /> New search
          </Link>
        </Button>
      </div>
    </header>
  );
}
