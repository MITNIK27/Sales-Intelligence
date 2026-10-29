import { Info } from "lucide-react";
import type { ReactNode } from "react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// A small (i) button that explains something in a sentence. Opens on hover and on keyboard focus,
// and has a label for screen readers, so the explanation is never mouse-only.
export function InfoTip({
  label,
  children,
  className,
}: {
  // What the button is for, read by screen readers, e.g. "About what was checked".
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={label}
            className={cn(
              "inline-flex size-5 items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-primary",
              className,
            )}
          >
            <Info className="size-4" aria-hidden="true" />
          </button>
        </TooltipTrigger>
        <TooltipContent className="block max-w-xs whitespace-normal text-left">
          {children}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
