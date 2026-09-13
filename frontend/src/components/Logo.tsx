import logoBlack from "@/assets/logo-black.svg";
import logoWhiteRed from "@/assets/logo-white-red.svg";
import { cn } from "@/lib/utils";

/**
 * InfoBeans logo. Brand rule: black wordmark on light grounds,
 * white/red wordmark on dark grounds. Never recolor the mark.
 */
export function Logo({ on = "light", className }: { on?: "light" | "dark"; className?: string }) {
  return (
    <img
      src={on === "dark" ? logoWhiteRed : logoBlack}
      alt="InfoBeans"
      className={cn("h-8 w-auto", className)}
    />
  );
}
