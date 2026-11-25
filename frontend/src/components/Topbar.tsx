import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet } from "@/api/client";
import { UserMenu } from "@/components/UserMenu";
import { Wordmark } from "@/components/Wordmark";
import { Button } from "@/components/ui/button";

type Health = "checking" | "online" | "offline";

// The product header: white, with a hairline and a soft shadow so it sits above the cream page. Left: the product's
// wordmark. Right: the server status (while developing, or when it cannot be reached), the one
// action useful from every page (start a new search) and your account.
export function Topbar({ limited = false }: { limited?: boolean }) {
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
    <header className="col-start-2 row-start-1 flex h-15 items-center justify-between gap-6 border-b border-border bg-card shadow-[0_1px_3px_rgb(47_47_57/0.06)] px-8">
      <Wordmark />

      <div className="flex shrink-0 items-center gap-3">
        {showStatus && (
          <span
            className="flex items-center gap-1.5 text-xs text-muted-foreground"
            role="status"
            aria-live="polite"
            title={
              health === "offline"
                ? "The server cannot be reached"
                : "Shown while developing"
            }
          >
            <span
              className={`inline-block size-1.5 rounded-full ${
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
          </span>
        )}
        {!limited && (
          <Button asChild size="sm" className="h-8 rounded-md px-3">
            <Link to="/market-discovery">
              <Plus className="size-4" /> New search
            </Link>
          </Button>
        )}
        <span className="h-6 w-px bg-border" aria-hidden="true" />
        <UserMenu limited={limited} />
      </div>
    </header>
  );
}

// The product's name as a mark, in Instrument Serif (used nowhere else): "Sales" upright,
// "Intelligence" italic in InfoBeans crimson. No tile or gradient.
