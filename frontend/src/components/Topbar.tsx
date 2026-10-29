import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet } from "@/api/client";
import { Button } from "@/components/ui/button";
import { APP_NAME } from "@/lib/app-meta";

type Health = "checking" | "online" | "offline";

// The product header. Left: the product name. Right: the one action useful from every page (start
// a new search) and, while developing or if the system cannot be reached, its status. A healthy
// production system shows no status at all. The gradient (white fading into the page's warm tint,
// with a crimson-to-amber line along the bottom) is the only decoration; nothing else is added.
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
    <header className="relative col-start-2 row-start-1 flex h-15 items-center justify-between gap-6 bg-linear-to-r from-card via-card to-accent px-8 shadow-sm">
      <p className="min-w-0 truncate bg-linear-to-r from-foreground to-primary bg-clip-text text-lg font-bold tracking-tight text-transparent">
        {APP_NAME}
      </p>

      <div className="flex shrink-0 items-center gap-4">
        {showStatus && (
          <div
            className="flex items-center gap-2 rounded-full border border-border bg-card/70 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur"
            role="status"
            aria-live="polite"
          >
            <span
              className={`inline-block size-2 rounded-full ${
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
        <Button
          asChild
          size="sm"
          className="rounded-full bg-linear-to-r from-primary to-[#ff5a3c] px-4 shadow-sm hover:brightness-95"
        >
          <Link to="/market-discovery">
            <Plus className="size-4" /> New search
          </Link>
        </Button>
      </div>

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 bg-linear-to-r from-primary via-[#ff5a3c] to-[#ffb347]"
      />
    </header>
  );
}
