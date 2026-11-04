import { Suspense, lazy, useMemo } from "react";

import { SkeletonLines } from "@/components/Skeleton";
import { buildGraph, type GraphInput } from "@/features/brief/graph/buildGraph";

// The map library is large, so it is only loaded when this section is opened.
const ConnectionMap = lazy(
  () => import("@/features/brief/graph/ConnectionMap"),
);

export function ConnectionMapSection({ input }: { input: GraphInput }) {
  const {
    companyName,
    industry,
    opportunity,
    fit,
    focus,
    tiering,
    recommendation,
  } = input;
  const graph = useMemo(
    () =>
      buildGraph({
        companyName,
        industry,
        opportunity,
        fit,
        focus,
        tiering,
        recommendation,
      }),
    [companyName, industry, opportunity, fit, focus, tiering, recommendation],
  );
  return (
    <Suspense fallback={<SkeletonLines lines={6} />}>
      <ConnectionMap graph={graph} />
    </Suspense>
  );
}
