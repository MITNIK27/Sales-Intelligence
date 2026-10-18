import type { ReactNode } from "react";

interface Props {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}

/** Consistent title/description/primary-action header — design-kit §5. */
export function PageHeader({ title, description, action }: Props) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold">{title}</h1>
        {description && (
          <p className="mt-1 text-base text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
