import { ExternalLink } from "lucide-react";

import { websiteLabel, websiteUrl } from "@/lib/url";
import { cn } from "@/lib/utils";

// A company's website as a link that opens in a new tab. Used wherever a domain is shown, so
// checking the real site is always one click away. Clicking it never triggers a clickable row.
export function WebsiteLink({
  domain,
  className,
  light = false,
}: {
  domain: string;
  className?: string;
  // On a dark background the link is white instead of the brand colour.
  light?: boolean;
}) {
  return (
    <a
      href={websiteUrl(domain)}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      title={`Open ${websiteLabel(domain)} in a new tab`}
      className={cn(
        "inline-flex items-center gap-1 hover:underline focus-visible:outline-2 focus-visible:outline-primary",
        light ? "text-white/80 hover:text-white" : "text-primary-text",
        className,
      )}
    >
      {websiteLabel(domain)}
      <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}
