import { APP_NAME } from "@/lib/app-meta";

export function Topbar() {
  return (
    <header className="col-start-2 row-start-1 flex h-15 items-center border-b border-border bg-card px-8">
      <span className="text-base font-semibold text-foreground">{APP_NAME}</span>
    </header>
  );
}
