import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { SkeletonLines } from "@/components/Skeleton";
import { Card } from "@/components/ui/card";
import { BriefBody } from "@/features/brief/BriefBody";
import { toggleId } from "@/features/brief/briefFilter";
import { BriefFilterBar } from "@/features/brief/BriefFilterBar";
import { StartBriefCard } from "@/features/brief/StartBriefCard";
import {
  briefTargets,
  doneOfferingIds,
  titleCaseArea,
} from "@/features/brief/startBrief";
import { useBriefFilter } from "@/features/brief/useBriefFilter";
import { useOfferingOptions } from "@/features/brief/useOfferingOptions";
import {
  groupOpportunities,
  pickOpportunity,
} from "@/features/brief/opportunityLabels";
import { useOpportunities } from "@/features/brief/useOpportunities";

// The Company Brief: one report for one company, about one offering filter and one opportunity
// area, used by both Quick Check and the company page. The filter bar stays in view; everything
// below it follows the two choices made there.
export function Brief({
  companyId,
  companyName = null,
  runOfferingIds = [],
  alwaysShow = false,
  onDataChanged,
}: {
  companyId: string;
  companyName?: string | null;
  runOfferingIds?: string[];
  alwaysShow?: boolean;
  // Called after something in the brief changed people or recommendations, so the page around
  // it can reload what it shows.
  onDataChanged?: () => void;
}) {
  const opps = useOpportunities(companyId);
  const offerings = useOfferingOptions();
  const filter = useBriefFilter(runOfferingIds, offerings.known);
  const [params, setParams] = useSearchParams();
  const { items, error } = opps;
  // Opened from a Market Discovery run, only that run's offerings are offered, with a way to see
  // the rest. Without a run there is nothing to narrow by, so every offering is listed.
  const [showAll, setShowAll] = useState(false);
  const fromRun = runOfferingIds.length > 0;
  // Offerings that already have a researched brief of their own are finished: they leave the list,
  // and a choice of one is dropped (this is what removes the filter once its search completes).
  const done = useMemo(
    () => doneOfferingIds(opps.items ?? [], offerings.products),
    [opps.items, offerings.products],
  );
  const pendingDone = filter.offeringIds.filter((id) => done.has(id));
  const dropKey = pendingDone.join(",");
  useEffect(() => {
    if (dropKey) {
      const gone = new Set(dropKey.split(","));
      filter.setIds(filter.offeringIds.filter((id) => !gone.has(id)));
    }
    // Only when a chosen offering becomes finished.
  }, [dropKey]);
  const available = offerings.options.filter((o) => !done.has(o.id));
  const offeringOptions =
    fromRun && !showAll
      ? available.filter(
          (o) =>
            runOfferingIds.includes(o.id) || filter.offeringIds.includes(o.id),
        )
      : available;

  if (items === null && error) {
    return (
      <Card className="mt-6">
        <ErrorState message={error} onRetry={opps.reload} />
      </Card>
    );
  }
  if (items === null) {
    return (
      <Card className="mt-6 p-6">
        <SkeletonLines lines={4} />
      </Card>
    );
  }

  const { general, active, suggested } = groupOpportunities(items);
  const areas = [...(general ? [general] : []), ...active, ...suggested];
  if (areas.length === 0 && !alwaysShow) return null;

  const selected = pickOpportunity(items, params.get("area"));

  const chooseArea = (id: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("area", id);
        return next;
      },
      { replace: true },
    );

  async function addArea(label: string) {
    const created = await opps.addArea(titleCaseArea(label));
    if (created) chooseArea(created.id);
  }

  // Research what we could offer the company as a whole, then show it on the overall view.
  async function findOffers() {
    const id = await opps.findOffers();
    if (id) chooseArea(id);
  }

  // Start a brief around one offering: its area (first area tag, or its name) is created,
  // researched and opened, and the offering becomes the one the brief is about.
  async function briefAround(productId: string) {
    const target = briefTargets([productId], offerings.products)[0];
    if (!target) return;
    filter.setIds([productId]);
    await addArea(target.areaLabel);
  }

  async function lookOverall() {
    if (general) chooseArea(general.id);
    else await opps.startOverall();
  }

  return (
    <section aria-label="Company brief" className="mt-2">
      <BriefFilterBar
        industry={selected?.industry_context ?? null}
        offeringOptions={offeringOptions}
        narrowed={fromRun ? !showAll : null}
        onToggleNarrowed={() => setShowAll((v) => !v)}
        offeringIds={filter.offeringIds}
        source={filter.source}
        onToggleOffering={(id) =>
          filter.setIds(toggleId(filter.offeringIds, id))
        }
        onClearOfferings={() => filter.setIds([])}
        areas={areas}
        areaId={selected?.id ?? null}
        researching={opps.researching}
        onSelectArea={chooseArea}
        onAddArea={addArea}
      />
      {error && (
        <p role="alert" className="mb-4 text-sm text-destructive">
          {error}
        </p>
      )}
      {selected === null ? (
        <StartBriefCard
          companyName={companyName}
          targets={briefTargets(filter.offeringIds, offerings.products)}
          onCreate={addArea}
          onOverall={lookOverall}
        />
      ) : (
        <BriefBody
          key={selected.id}
          opportunity={selected}
          companyName={companyName}
          areas={areas}
          offeringIds={filter.offeringIds}
          offeringTargets={Object.fromEntries(
            briefTargets(
              offeringOptions.map((o) => o.id),
              offerings.products,
            ).map((t) => [t.id, t]),
          )}
          researching={opps.researching.has(selected.id)}
          suggesting={opps.suggesting}
          onResearch={() => opps.research(selected.id, !!selected.assessment)}
          onPickArea={chooseArea}
          onOverall={lookOverall}
          onSuggest={opps.suggest}
          findingOffers={opps.findingOffers}
          onFindOffers={findOffers}
          onBriefAround={briefAround}
          onChanged={() => {
            opps.reload();
            onDataChanged?.();
          }}
        />
      )}
    </section>
  );
}
