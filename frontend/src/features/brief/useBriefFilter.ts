import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import {
  parseIds,
  resolveOfferings,
  serializeIds,
  type Resolved,
} from "@/features/brief/briefFilter";
import { usePersistentState } from "@/lib/usePersistentState";

const SAVED_KEY = "brief.offerings";

// The offerings the brief is about, kept in the address (so a link reopens the same view) and
// remembered in the browser. Opened from a Market Discovery run, the run's offerings apply until
// the person chooses otherwise. `known` (the offerings that still exist) filters out stale ids.
export function useBriefFilter(runIds: string[], known: Set<string> | null) {
  const [params, setParams] = useSearchParams();
  const [saved, setSaved] = usePersistentState<string[]>(SAVED_KEY, []);

  const urlRaw = params.get("offerings");
  const runKey = runIds.join(",");
  const resolved: Resolved = useMemo(
    () =>
      resolveOfferings({
        urlIds: parseIds(urlRaw),
        runIds: runKey ? runKey.split(",") : [],
        savedIds: saved,
        known,
      }),
    [urlRaw, runKey, saved, known],
  );

  const setIds = useCallback(
    (ids: string[]) => {
      setSaved(ids);
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (ids.length > 0) next.set("offerings", serializeIds(ids));
          else next.delete("offerings");
          return next;
        },
        { replace: true },
      );
    },
    [setParams, setSaved],
  );

  return { offeringIds: resolved.ids, source: resolved.source, setIds };
}
