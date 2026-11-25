import { Link } from "react-router-dom";

import { APP_NAME } from "@/lib/app-meta";
import { cn } from "@/lib/utils";

// The product's name as its logo: Instrument Serif, "Sales" upright and "Intelligence" in italic
// crimson. In the top bar it links home; on the sign-in page it is plain and larger.
export function Wordmark({
  size = "md",
  link = true,
}: {
  size?: "md" | "lg" | "xl";
  link?: boolean;
}) {
  const text =
    size === "xl"
      ? "text-[52px]"
      : size === "lg"
        ? "text-[40px]"
        : "text-[26px]";
  const content = (
    <>
      <span className={cn(text, "text-foreground")}>Sales</span>
      <span className={cn(text, "italic text-primary-text")}>Intelligence</span>
    </>
  );
  const base =
    "flex items-baseline gap-1.5 whitespace-nowrap font-['Instrument_Serif',serif] leading-none";

  if (!link) return <p className={base}>{content}</p>;
  return (
    <Link
      to="/"
      aria-label={`${APP_NAME} home`}
      className={cn(
        base,
        "rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary",
      )}
    >
      {content}
    </Link>
  );
}
