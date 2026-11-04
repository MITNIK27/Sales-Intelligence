import { useMemo, useState } from "react";

import type { CompanyOpportunity } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { OfferingPrompt } from "@/features/brief/OfferingPrompt";
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
  onFindOffers,
  onBriefAround,
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
  onFindOffers: () => void;
  onBriefAround: (productId: string) => Promise<void>;
  onChanged: () => void;
}) {
  const detail = useBriefDetail(opportunity.id, offeringIds, onChanged);
  const contacts = useMemo(() => detail.contacts ?? [], [detail.contacts]);
  const tiering = useMemo(() => tierPeople(contacts), [contacts]);
  // The same array between renders, so the connection map is not rebuilt (and redrawn) each time.
  const fitList = useMemo(() => detail.fit ?? [], [detail.fit]);
  const [declined, setDeclined] = useState<string[]>([]);
  const overall = opportunity.area_key === "general";
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

  if (overall) {
    return (
      <div>
        <h2 className="mb-4 text-xl font-bold">
          {companyName ? `${companyName}: ` : ""}the company as a whole
        </h2>
        {notices}
        <OfferIdeas
          fit={detail.fit}
          finding={findingOffers}
          onFind={onFindOffers}
          onBriefAround={onBriefAround}
        />
        <Card className="mb-6">
          <CardContent>
            <h2 className="text-lg font-bold">Go deeper on one area</h2>
            <p className="mb-3 text-sm text-muted-foreground">
              Add an area above, or use a suggested one, to see what they are
              doing there, the connection map and what to say.
            </p>
            <Button variant="outline" disabled={suggesting} onClick={onSuggest}>
              {suggesting ? "Looking…" : "Suggest areas from the evidence"}
            </Button>
          </CardContent>
        </Card>
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

  // The chosen offering, if any, that nothing has been looked at for yet: no judgement in this
  // area, and this area is not already the one made for it.
  const unsearched =
    detail.fit === null
      ? null
      : (offeringIds
          .map((id) => offeringTargets[id])
          .find(
            (t) =>
              t &&
              !declined.includes(t.id) &&
              t.areaLabel.toLowerCase() !==
                opportunity.area_label.toLowerCase() &&
              !detail.fit?.some((f) => f.product_id === t.id),
          ) ?? null);
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
        <h2 className="text-xl font-bold">
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
      {unsearched && (
        <OfferingPrompt
          target={unsearched}
          companyName={companyName}
          onYes={() => onBriefAround(unsearched.id)}
          onNo={() => setDeclined((d) => [...d, unsearched.id])}
        />
      )}
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
