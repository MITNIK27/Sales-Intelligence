import { useState } from "react";

import { cn } from "@/lib/utils";

// The company's logo, taken from its website address, with its first letter as the fallback when
// there is no address or no picture loads. The picture comes from Google's favicon service, so the
// browser asks Google for the logo of that domain (a company domain, never a person's details).
export function CompanyLogo({
  name,
  domain,
  className,
}: {
  name: string;
  domain: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const host = domain
    ? domain
        .replace(/^https?:\/\//i, "")
        .replace(/^www\./i, "")
        .split("/")[0]
    : "";
  const letter = name.trim().charAt(0).toUpperCase() || "?";

  if (!host || failed) {
    return (
      <span
        aria-hidden="true"
        className={cn(
          "flex size-12 shrink-0 items-center justify-center bg-primary/10 text-lg font-bold text-primary-text",
          className,
        )}
      >
        {letter}
      </span>
    );
  }
  return (
    <img
      src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=128`}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className={cn(
        "size-12 shrink-0 border border-border bg-white object-contain p-1",
        className,
      )}
    />
  );
}
