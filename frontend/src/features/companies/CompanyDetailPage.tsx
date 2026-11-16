import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { PipelineStatusStepper } from "@/components/PipelineStatusStepper";
import { SkeletonLines } from "@/components/Skeleton";
import { Tabs } from "@/components/Tabs";
import { Card } from "@/components/ui/card";
import { useCompanyActions } from "@/features/companies/hooks/useCompanyActions";
import { useCompanyData } from "@/features/companies/hooks/useCompanyData";
import { useEnrichmentJob } from "@/features/companies/hooks/useEnrichmentJob";
import { Brief } from "@/features/brief/Brief";
import { DismissedBanner } from "@/features/companies/notAFit/DismissedBanner";
import { QuickCheckSaid } from "@/features/companies/notAFit/QuickCheckSaid";
import { useBuyingRoles } from "@/features/brief/useBuyingRoles";
import { useRunOfferings } from "@/features/brief/useRunOfferings";
import { useSearchContext } from "@/features/brief/useSearchContext";
import { COMPANY_TABS, tabFromParams } from "@/features/companies/lib/tabs";
import { buildPipelineSteps } from "@/features/companies/lib/pipelineSteps";
import { CompanyHeader } from "@/features/companies/sections/CompanyHeader";
import { CompanyOverview } from "@/features/companies/sections/CompanyOverview";
import { ContactsSection } from "@/features/companies/sections/ContactsSection";
import { EnrichmentPanel } from "@/features/companies/sections/EnrichmentPanel";
import { PeopleCommittee } from "@/features/companies/sections/PeopleCommittee";
import { QualificationSection } from "@/features/companies/sections/QualificationSection";
import { RecommendationsSection } from "@/features/companies/sections/RecommendationsSection";
import { SignalsSection } from "@/features/companies/sections/SignalsSection";

const BackLink = () => (
  <Link
    to="/companies"
    className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
  >
    <ArrowLeft className="size-4" /> Back to companies
  </Link>
);

// One company: what we know, who is there, and what to say. This file only composes the page;
// loading lives in useCompanyData, actions in useCompanyActions, the scrape job in
// useEnrichmentJob, and each section is its own component under sections/.
export function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = tabFromParams(searchParams);
  // The offerings the company was searched for: from the run in the address when there is one,
  // otherwise from the company's own latest run, so it works however the company was opened.
  const urlOfferings = useRunOfferings(searchParams.get("run"));
  const { context: searchContext } = useSearchContext(companyId ?? null);
  const runOfferings =
    urlOfferings.length > 0
      ? urlOfferings
      : (searchContext?.runs[0]?.offerings ?? []).map((o) => ({
          id: o.product_id,
          name: o.name,
          kind: o.kind,
        }));
  const [rolesVersion, setRolesVersion] = useState(0);
  const buyingRoles = useBuyingRoles(
    companyId ?? "",
    !!companyId,
    runOfferings.map((o) => o.id),
    rolesVersion,
  );
  const data = useCompanyData(companyId);
  const actions = useCompanyActions(companyId, data);
  const enrichment = useEnrichmentJob(
    companyId,
    data.company?.enrichment_status,
    {
      reloadCompany: data.reloadCompany,
      refreshCompany: data.refreshCompany,
      reloadSignals: data.reloadSignals,
      onError: data.setError,
    },
  );
  const { company } = data;

  if (data.error) {
    return (
      <div>
        <BackLink />
        <Card>
          <ErrorState message={data.error} onRetry={data.reloadCompany} />
        </Card>
      </div>
    );
  }

  if (!company) {
    return (
      <div>
        <BackLink />
        <Card className="p-6">
          <SkeletonLines lines={6} />
        </Card>
      </div>
    );
  }

  const steps = buildPipelineSteps({
    enrichmentStatus: company.enrichment_status,
    enrichmentError: company.enrichment_error,
    contactCount: company.contacts.length,
    latestQualification: data.qualificationResults?.[0] ?? null,
    rolesClassifiedCount: Math.max(
      Object.keys(data.roleRelevanceByContact).length,
      Object.values(buyingRoles).filter((r) => r.role).length,
    ),
    draftsGeneratedCount: (data.drafts ?? []).filter(
      (d) => d.status !== "discarded",
    ).length,
  });

  return (
    <div>
      <BackLink />
      <CompanyHeader
        company={company}
        products={
          data.products && runOfferings.length > 0
            ? data.products.filter((p) =>
                runOfferings.some((o) => o.id === p.id),
              )
            : data.products
        }
        fromRun={runOfferings.length > 0}
        onConfirm={actions.confirmWholeCompany}
        onDismissed={() => {
          void data.refreshCompany();
        }}
      />
      {company.dismissed_at && (
        <DismissedBanner
          reason={company.dismissed_reason}
          note={company.dismissed_note}
          dismissedAt={company.dismissed_at}
          onRestore={actions.restore}
        />
      )}
      <QuickCheckSaid note={company.quick_check} />
      <div className="mb-6">
        <PipelineStatusStepper steps={steps} />
      </div>
      <Tabs
        label="Company sections"
        trailing={
          company.industry ? (
            <>
              Industry:{" "}
              <span className="text-foreground">{company.industry}</span>
            </>
          ) : undefined
        }
        tabs={COMPANY_TABS}
        active={tab}
        onChange={(id) =>
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev);
              next.set("tab", id);
              return next;
            },
            { replace: true },
          )
        }
      />
      {tab === "overview" && (
        <>
          <CompanyOverview company={company} />
          <EnrichmentPanel
            company={company}
            scrapeJob={enrichment.scrapeJob}
            triggering={enrichment.triggering}
            onScrape={enrichment.start}
          />
          <SignalsSection
            company={company}
            signals={data.signals}
            error={data.signalsError}
            onRetry={data.reloadSignals}
          />
          <QualificationSection
            results={data.qualificationResults}
            error={data.qualificationResultsError}
            criteria={company.criteria ?? []}
            onSaveCriteria={actions.saveCriteria}
            onCheck={actions.runQualification}
            onRetry={data.reloadQualificationResults}
          />
        </>
      )}
      {tab === "opportunity" && (
        <Brief
          companyId={company.id}
          companyName={company.name}
          runOfferingIds={runOfferings.map((o) => o.id)}
          alwaysShow
          showIndustry={false}
          onDataChanged={() => {
            data.reloadCompany();
            data.reloadRecommendations();
            setRolesVersion((v) => v + 1);
          }}
        />
      )}
      {tab === "people" && (
        <>
          <PeopleCommittee
            companyId={company.id}
            onChanged={() => {
              data.reloadCompany();
              data.reloadRecommendations();
              setRolesVersion((v) => v + 1);
            }}
          >
            {(committee, tools) => (
              <ContactsSection
                company={company}
                products={data.products}
                roleRelevanceByContact={data.roleRelevanceByContact}
                buyingRoles={buyingRoles}
                committee={committee}
                tools={tools}
                roleRelevanceError={data.roleRelevanceError}
                activeRoleCategoriesCount={data.activeRoleCategoriesCount}
                onSearch={actions.findContacts}
                onClassify={actions.runRoleClassification}
                onConfirmContact={actions.confirmOneContact}
                onRemoveContact={actions.removeOneContact}
                onOutreachLogged={actions.outreachLogged}
              />
            )}
          </PeopleCommittee>
        </>
      )}
      {tab === "recommendations" && (
        <RecommendationsSection
          companyId={company.id}
          recommendations={data.recommendations}
          error={data.recommendationsError}
          products={data.products}
          onGenerate={actions.createRecommendation}
          onRetry={data.reloadRecommendations}
        />
      )}
    </div>
  );
}
