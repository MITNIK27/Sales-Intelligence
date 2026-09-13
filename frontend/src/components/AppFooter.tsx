import { APP_VERSION, COPYRIGHT_OWNER, COPYRIGHT_YEAR } from "@/lib/app-meta";
import { cn } from "@/lib/utils";

export function AppFooter({ className }: { className?: string }) {
  return (
    <footer
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 border-t border-border px-8 py-4 text-xs text-muted-foreground",
        className,
      )}
    >
      <span>
        Copyright © {COPYRIGHT_YEAR}{" "}
        <span className="font-medium text-foreground">{COPYRIGHT_OWNER}</span>. All rights
        reserved.
      </span>
      <span>Version {APP_VERSION}</span>
    </footer>
  );
}
