import { X } from "lucide-react";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type ToastVariant = "error" | "success";

type ToastInput = {
  description: string;
  variant?: ToastVariant;
};

type ToastItem = ToastInput & { id: number };

type ToastContextValue = {
  showToast: (toast: ToastInput) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 5000;

const VARIANT_CLASSES: Record<ToastVariant, string> = {
  error: "border-destructive/30 bg-card text-destructive",
  success: "border-success/30 bg-card text-success",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    ({ description, variant = "error" }: ToastInput) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, description, variant }]);
      window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="alert"
            className={cn(
              "flex items-start gap-3 rounded-lg border p-3 text-sm shadow-lg",
              VARIANT_CLASSES[t.variant ?? "error"],
            )}
          >
            <span className="flex-1">{t.description}</span>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
