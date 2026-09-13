import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  message: string;
  onRetry?: () => void;
}

/** Say what failed and how to recover, then offer a retry action — design-kit §6. */
export function ErrorState({ message, onRetry }: Props) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="grid size-12 place-items-center bg-secondary">
        <AlertTriangle className="size-6 text-destructive" />
      </div>
      <div>
        <h3 className="text-lg font-bold">Something went wrong</h3>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
