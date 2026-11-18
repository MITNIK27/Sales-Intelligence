import { useMemo, type ReactNode } from "react";

import type { CompanyOpportunity } from "@/api/types";
import { Button } from "@/components/ui/button";
import { BestOffering } from "@/features/brief/BestOffering";
import { BriefSection } from "@/features/brief/BriefSection";
import {
  hasGaps,
  sectionSummary,
  sectionTitle,
  visibleSections,
  type SectionId,
} from "@/features/brief/briefSections";
import { CopyBrief } from "@/features/brief/CopyBrief";
import { AngleBody } from "@/features/brief/DifferentBasis";
import { FindingsList } from "@/features/brief/FindingsList";
import { GapsBody } from "@/features/brief/GapsCard";
import { ConnectionMapSection } from "@/features/brief/graph/ConnectionMapSection";
import { OfferIdeas } from "@/features/brief/OfferIdeas";
import { ResearchCard } from "@/features/brief/ResearchCard";
import { SayBody } from "@/features/brief/SayBody";
import { StartWith } from "@/features/brief/StartWith";
import { tierPeople } from "@/features/brief/tiers";
import type { BriefTarget } from "@/features/brief/startBrief";
import { titleCaseArea } from "@/features/brief/startBrief";
import { OverallSummary } from "@/features/brief/OverallSummary";
import { RelatedPick } from "@/features/brief/RelatedPick";
import { useBriefDetail } from "@/features/brief/useBriefDetail";

// One opportunity, written up as a report that only shows what exists. A new area shows a single
// card to research it; after that, collapsible sections appear as there is something to say.
export function BriefBody({
  opportunity,
  companyName,
  areas,
  offeringIds,
  offeringTargets,
  researching,
  suggesting,
  onResearch,
  onPickArea,
  onOverall,
  onSuggest,
  findingOffers,
  offersNotice,
  onFindOffers,
  onBriefAround,
  overallTop,
  overallBottom,
  onChanged,
}: {
  opportunity: CompanyOpportunity;
  companyName: string | null;
  areas: CompanyOpportunity[];
  offeringIds: string[];
  // For each offering, its name and the area a brief around it would research.
  offeringTargets: Record<string, BriefTarget>;
  researching: boolean;
  suggesting: boolean;
  onResearch: () => void;
  onPickArea: (id: string) => void;
  onOverall: () => void;
  onSuggest: () => void;
  findingOffers: boolean;
  offersNotice: string | null;
  onFindOffers: () => void;
  onBriefAround: (productId: string) => Promise<void>;
  // Overall view only: what was searched (above the summary) and recommended areas (below the offerings).
  overallTop?: ReactNode;
  overallBottom?: ReactNode;
  onChanged: () => void;
}) {
  const overall = opportunity.area_key === "general";
  // A picked offering belongs to its own area. Inside another area it is not made the lead offering
  // (that would judge it, and lead with it, where the evidence is about something else); it is
  // shown as a related pick instead. The overall view is about every offering, so all picks count.
  const sameArea = (t: BriefTarget) =>
    t.areaLabel.trim().toLowerCase() ===
    opportunity.area_label.trim().toLowerCase();
  const picks = offeringIds
    .map((id) => offeringTargets[id])
    .filter((t): t is BriefTarget => Boolean(t));
  const ownIds = overall
    ? offeringIds
    : picks.filter(sameArea).map((t) => t.id);
  const related = overall ? [] : picks.filter((t) => !sameArea(t));
  const detail = useBriefDetail(opportunity.id, ownIds, onChanged);
  const contacts = useMemo(() => detail.contacts ?? [], [detail.contacts]);
  const tiering = useMemo(() => tierPeople(contacts), [contacts]);
  // The same array between renders, so the connection map is not rebuilt (and redrawn) each time.
  const fitList = useMemo(() => detail.fit ?? [], [detail.fit]);
  const researched = opportunity.assessment !== null;
  const lead =
    tiering.tiers
      .flatMap((t) => t.people)
      .find((p) => p.contact_id === tiering.approachFirst) ?? null;

  const notices = (
    <>
      {detail.error && (
        <p role="alert" className="mb-4 text-sm text-destructive">
          {detail.error}
        </p>
      )}
      {detail.notice && (
        <p
          role="status"
          className="mb-4 border-l-2 border-border pl-3 text-sm text-muted-foreground"
        >
          {detail.notice}
        </p>
      )}
    </>
  );

  const chosen = offeringIds
    .map((id) => offeringTargets[id])
    .filter((t): t is BriefTarget => Boolean(t))
    .map((t) => ({ id: t.id, name: t.name }));
  const chosenNames = chosen.map((c) => c.name);

  if (overall) {
    return (
      <div>
        {notices}
        {overallTop}
        <OverallSummary
          opportunity={opportunity}
          companyName={companyName}
          chosenNames={chosenNames}
          finding={findingOffers}
          notice={offersNotice}
          onFind={onFindOffers}
        />
        <OfferIdeas
          companyName={companyName}
          fit={detail.fit}
          chosen={chosen}
          onBriefAround={onBriefAround}
        />
        {overallBottom}
      </div>
    );
  }

  if (!researched) {
    return (
      <div>
        {notices}
        <ResearchCard
          opportunity={opportunity}
          companyName={companyName}
          researching={researching}
          onResearch={onResearch}
        />
      </div>
    );
  }

  const visible = visibleSections({
    researched,
    judged: detail.focus !== null,
    peopleKnown: contacts.length,
    recommended: detail.recommendation !== null,
    hasGaps: hasGaps(opportunity),
  });
  const summaryData = {
    opportunity,
    focus: detail.focus,
    lead,
    peopleKnown: contacts.length,
    recommendation: detail.recommendation,
  };

  function actionFor(id: SectionId) {
    if (id === "doing")
      return (
        <Button
          variant="outline"
          size="sm"
          disabled={researching}
          onClick={onResearch}
        >
          {researching ? "Researching…" : "Research again"}
        </Button>
      );
    if (id === "say" && detail.focus) {
      const product = detail.focus;
      return (
        <Button
          size="sm"
          variant={detail.recommendation ? "outline" : "default"}
          disabled={detail.busy === "recommend"}
          onClick={() => detail.recommend(product.product_id)}
        >
          {detail.busy === "recommend"
            ? "Writing…"
            : detail.recommendation
              ? "Refresh"
              : `Write for ${product.product_name}`}
        </Button>
      );
    }
    return undefined;
  }

  function bodyFor(id: SectionId) {
    switch (id) {
      case "doing":
        return <FindingsList opportunity={opportunity} />;
      case "map":
        return (
          <ConnectionMapSection
            input={{
              companyName: companyName ?? "The company",
              industry: opportunity.industry_context,
              opportunity,
              fit: fitList,
              focus: detail.focus,
              tiering,
              recommendation: detail.recommendation,
            }}
          />
        );
      case "offering":
        return (
          <BestOffering
            focus={detail.focus}
            fit={fitList}
            working={detail.busy === "analyse"}
            onWorkOut={(force) => detail.analyse(force)}
          />
        );
      case "start":
        return (
          <StartWith
            lead={lead}
            peopleKnown={contacts.length}
            companyId={opportunity.company_id}
          />
        );
      case "say":
        return <SayBody recommendation={detail.recommendation} />;
      case "gaps":
        return <GapsBody opportunity={opportunity} />;
      case "angle":
        return (
          <AngleBody
            areas={areas}
            areaId={opportunity.id}
            suggesting={suggesting}
            onPickArea={onPickArea}
            onOverall={onOverall}
            onSuggest={onSuggest}
          />
        );
    }
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">
          {companyName ? `${companyName}: ` : ""}
          {titleCaseArea(opportunity.area_label)}
        </h2>
        <CopyBrief
          companyName={companyName}
          opportunity={opportunity}
          fit={detail.focus}
          contacts={contacts}
          recommendation={detail.recommendation}
        />
      </div>
      {notices}
      {related.map((t) => (
        <RelatedPick
          key={t.id}
          target={t}
          areaLabel={opportunity.area_label}
          fit={detail.fit?.find((f) => f.product_id === t.id)}
          ownArea={
            areas.find(
              (o) =>
                o.area_label.trim().toLowerCase() ===
                t.areaLabel.trim().toLowerCase(),
            ) ?? null
          }
          onOpen={onPickArea}
          onStart={() => onBriefAround(t.id)}
        />
      ))}
      {visible.map((id, index) => (
        <BriefSection
          key={id}
          number={index + 1}
          title={sectionTitle(id, companyName)}
          summary={sectionSummary(id, summaryData)}
          action={actionFor(id)}
          defaultOpen={index === 0}
        >
          {bodyFor(id)}
        </BriefSection>
      ))}
    </div>
  );
}
