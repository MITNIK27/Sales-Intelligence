import { cn } from "@/lib/utils";

/** Motion-safe skeleton block — design-kit §6 loading pattern. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("h-4 rounded bg-muted motion-safe:animate-pulse", className)} />;
}

/** A stack of skeleton lines, for a card/table body that's still loading. */
export function SkeletonLines({ lines = 4, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={i % 2 === 1 ? "w-3/5" : "w-4/5"} />
      ))}
    </div>
  );
}
