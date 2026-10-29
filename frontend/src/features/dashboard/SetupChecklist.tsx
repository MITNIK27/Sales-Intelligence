import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

type Setup = {
  products: number;
  active_criteria: number;
  active_role_categories: number;
};

// First-run guidance, shown only while something is missing: one line pointing at the next step.
export function SetupChecklist({ setup }: { setup: Setup | null }) {
  if (!setup) return null;
  const steps = [
    { done: setup.products > 0, label: "Add your services and products", to: "/products" },
    {
      done: setup.active_criteria > 0,
      label: "Set your qualification criteria",
      to: "/qualification/criteria",
    },
    {
      done: setup.active_role_categories > 0,
      label: "Choose who to talk to",
      to: "/role-categories",
    },
  ];
  const next = steps.find((step) => !step.done);
  if (!next) return null;
  const left = steps.filter((step) => !step.done).length;
  return (
    <Link
      to={next.to}
      className="flex items-center justify-between gap-3 border border-border bg-card px-5 py-3 text-sm transition-colors duration-200 hover:border-primary hover:bg-primary/5 focus-visible:outline-2 focus-visible:outline-primary"
    >
      <span>
        <span className="text-muted-foreground">
          Setup · {left} {left === 1 ? "step" : "steps"} left —{" "}
        </span>
        <span className="font-medium">{next.label}</span>
      </span>
      <ArrowRight
        className="size-4 shrink-0 text-primary-text"
        aria-hidden="true"
      />
    </Link>
  );
}
