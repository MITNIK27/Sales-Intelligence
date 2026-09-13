import { ArrowLeft, ClipboardCheck, Lightbulb, Radar, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiGet, apiPost } from "@/api/client";
import type {
  CompanyDetail,
  Contact,
  JobStatus,
  Product,
  ProductList,
  QualificationCriterionList,
  QualificationResult,
  Recommendation,
  RecommendationGenerateRequest,
  RoleCategoryList,
  RoleRelevanceResult,
  ScrapeJobStarted,
  Signal,
} from "@/api/types";
import { ContactOutreachPanel } from "@/features/outreach/ContactOutreachPanel";
import { QualificationResultsTable } from "@/features/qualification/QualificationResultsTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonLines } from "@/components/Skeleton";
import {
  EnrichmentStatusBadge,
  NeedsReviewBadge,
  RolePriorityBadge,
  SignalTypeBadge,
} from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const POLL_INTERVAL_MS = 1500;

export function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scrapeJob, setScrapeJob] = useState<JobStatus | null>(null);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<number | null>(null);

  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null);
  const [recommendationsError, setRecommendationsError] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const [qualificationResults, setQualificationResults] = useState<QualificationResult[] | null>(
    null,
  );
  const [qualificationResultsError, setQualificationResultsError] = useState<string | null>(null);
  const [activeCriteriaCount, setActiveCriteriaCount] = useState<number | null>(null);
  const [checkingQualification, setCheckingQualification] = useState(false);
  const [checkQualificationError, setCheckQualificationError] = useState<string | null>(null);

  const [roleRelevanceByContact, setRoleRelevanceByContact] = useState<
    Record<string, RoleRelevanceResult>
  >({});
  const [roleRelevanceError, setRoleRelevanceError] = useState<string | null>(null);
  const [activeRoleCategoriesCount, setActiveRoleCategoriesCount] = useState<number | null>(null);
  const [classifyingRoles, setClassifyingRoles] = useState(false);
  const [classifyRolesError, setClassifyRolesError] = useState<string | null>(null);

  function loadCompany() {
    if (!companyId) return;
    setError(null);
    return apiGet<CompanyDetail>(`/companies/${companyId}`)
      .then(setCompany)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load company"));
  }

  function loadSignals() {
    if (!companyId) return;
    return apiGet<Signal[]>(`/companies/${companyId}/signals`).then(setSignals).catch(() => {
      // Signals are a supplementary section — a failure here shouldn't block the rest of the page.
    });
  }

  function loadRecommendations() {
    if (!companyId) return;
    setRecommendationsError(null);
    return apiGet<Recommendation[]>(`/companies/${companyId}/recommendations`)
      .then(setRecommendations)
      .catch((err) =>
        setRecommendationsError(
          err instanceof Error ? err.message : "failed to load recommendations",
        ),
      );
  }

  function loadProducts() {
    return apiGet<ProductList>("/products")
      .then((list) => setProducts(list.items))
      .catch(() => {
        // The product select is supplementary — a failure here shouldn't block the rest of the page.
      });
  }

  function loadQualificationResults() {
    if (!companyId) return;
    setQualificationResultsError(null);
    return apiGet<QualificationResult[]>(`/companies/${companyId}/qualification-results`)
      .then(setQualificationResults)
      .catch((err) =>
        setQualificationResultsError(
          err instanceof Error ? err.message : "failed to load qualification results",
        ),
      );
  }

  function loadActiveCriteriaCount() {
    return apiGet<QualificationCriterionList>("/qualification/criteria")
      .then((list) => setActiveCriteriaCount(list.items.filter((c) => c.is_active).length))
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
  }

  function loadRoleRelevanceResults() {
    if (!companyId) return;
    setRoleRelevanceError(null);
    return apiGet<RoleRelevanceResult[]>(`/companies/${companyId}/role-relevance`)
      .then((results) => {
        const byContact: Record<string, RoleRelevanceResult> = {};
        for (const result of results) byContact[result.contact_id] = result;
        setRoleRelevanceByContact(byContact);
      })
      .catch((err) =>
        setRoleRelevanceError(
          err instanceof Error ? err.message : "failed to load role classifications",
        ),
      );
  }

  function loadActiveRoleCategoriesCount() {
    return apiGet<RoleCategoryList>("/role-categories")
      .then((list) => setActiveRoleCategoriesCount(list.items.filter((c) => c.is_active).length))
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
  }

  useEffect(() => {
    loadCompany();
    loadSignals();
    loadRecommendations();
    loadProducts();
    loadQualificationResults();
    loadActiveCriteriaCount();
    loadRoleRelevanceResults();
    loadActiveRoleCategoriesCount();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [companyId]);

  async function handleGenerateRecommendation() {
    if (!companyId || !selectedProductId) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const body: RecommendationGenerateRequest = { product_id: selectedProductId };
      const recommendation = await apiPost<Recommendation>(
        `/companies/${companyId}/recommendations`,
        body,
      );
      setRecommendations((prev) => (prev ? [recommendation, ...prev] : [recommendation]));
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "failed to generate recommendation");
    } finally {
      setGenerating(false);
    }
  }

  async function handleCheckQualification() {
    if (!companyId) return;
    setCheckingQualification(true);
    setCheckQualificationError(null);
    try {
      const result = await apiPost<QualificationResult>(
        `/companies/${companyId}/qualification-results`,
      );
      setQualificationResults((prev) => (prev ? [result, ...prev] : [result]));
    } catch (err) {
      setCheckQualificationError(
        err instanceof Error ? err.message : "failed to check qualification",
      );
    } finally {
      setCheckingQualification(false);
    }
  }

  async function handleClassifyRoles() {
    if (!companyId) return;
    setClassifyingRoles(true);
    setClassifyRolesError(null);
    try {
      const results = await apiPost<RoleRelevanceResult[]>(
        `/companies/${companyId}/role-relevance`,
      );
      setRoleRelevanceByContact((prev) => {
        const next = { ...prev };
        for (const result of results) next[result.contact_id] = result;
        return next;
      });
    } catch (err) {
      setClassifyRolesError(err instanceof Error ? err.message : "failed to classify roles");
    } finally {
      setClassifyingRoles(false);
    }
  }

  function handleOutreachLogged(updatedContact: Contact) {
    setCompany((prev) =>
      prev
        ? {
            ...prev,
            contacts: prev.contacts.map((c) => (c.id === updatedContact.id ? updatedContact : c)),
          }
        : prev,
    );
  }

  async function handleScrape() {
    if (!companyId) return;
    setTriggering(true);
    setScrapeJob(null);
    try {
      const started = await apiPost<ScrapeJobStarted>(`/companies/${companyId}/scrape`);
      await loadCompany(); // reflects enrichment_status -> "pending" immediately
      pollRef.current = window.setInterval(async () => {
        const status = await apiGet<JobStatus>(`/jobs/${started.job_id}`);
        setScrapeJob(status);
        if (status.status === "done" || status.status === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          await loadCompany();
          await loadSignals();
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to start scrape");
    } finally {
      setTriggering(false);
    }
  }

  const backLink = (
    <Link
      to="/companies"
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" /> Back to companies
    </Link>
  );

  if (error) {
    return (
      <div>
        {backLink}
        <Card>
          <ErrorState message={error} onRetry={loadCompany} />
        </Card>
      </div>
    );
  }

  if (!company) {
    return (
      <div>
        {backLink}
        <Card className="p-6">
          <SkeletonLines lines={6} />
        </Card>
      </div>
    );
  }

  const scrapeInFlight = company.enrichment_status === "pending" || triggering;

  return (
    <div>
      {backLink}
      <PageHeader
        eyebrow="Company"
        title={
          <span className="inline-flex items-center gap-2">
            {company.name}
            {company.needs_review && <NeedsReviewBadge reason={company.needs_review_reason} />}
          </span>
        }
      />

      <Card>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Domain</dt>
            <dd>{company.domain ?? "—"}</dd>
            <dt className="text-muted-foreground">Industry</dt>
            <dd>{company.industry ?? "—"}</dd>
            <dt className="text-muted-foreground">Employee count</dt>
            <dd>{company.employee_count_range ?? "—"}</dd>
            {company.description && (
              <>
                <dt className="text-muted-foreground">Description</dt>
                <dd>{company.description}</dd>
              </>
            )}
          </dl>
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardContent>
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <EnrichmentStatusBadge status={company.enrichment_status} />
              {company.last_enriched_at && (
                <span className="text-sm text-muted-foreground">
                  last enriched {new Date(company.last_enriched_at).toLocaleString()}
                </span>
              )}
            </div>
            <Button type="button" onClick={handleScrape} disabled={scrapeInFlight}>
              {scrapeInFlight
                ? "Scraping…"
                : company.enrichment_status === "never_enriched"
                  ? "Scrape"
                  : "Re-scrape"}
            </Button>
          </div>
          {company.enrichment_status === "failed" && company.enrichment_error && (
            <p className="mt-3 text-sm text-destructive">{company.enrichment_error}</p>
          )}
          {scrapeJob?.status === "running" && scrapeJob.progress && (
            <p className="mt-3 text-sm text-muted-foreground">
              Step {scrapeJob.progress.done} of {scrapeJob.progress.total}…
            </p>
          )}
        </CardContent>
      </Card>

      <h2 className="mb-3 mt-8 text-lg font-bold">Signals</h2>
      <Card className={signals && signals.length > 0 ? "p-0" : undefined}>
        {!signals || signals.length === 0 ? (
          <EmptyState
            icon={Radar}
            title="No buying signals found yet"
            description="News mentions and hiring signals will appear here once found."
          />
        ) : (
          <ul className="divide-y divide-border">
            {signals.map((signal, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 px-4 py-3">
                <SignalTypeBadge type={signal.signal_type} />
                <span className="text-sm">{signal.text}</span>
                {signal.date && (
                  <span className="text-sm text-muted-foreground">— {signal.date}</span>
                )}
                <a
                  href={signal.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-muted-foreground hover:text-primary-text hover:underline"
                >
                  (source)
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="mb-3 mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">Contacts</h2>
        {company.contacts.length > 0 && (
          <Button
            type="button"
            size="sm"
            onClick={handleClassifyRoles}
            disabled={classifyingRoles || activeRoleCategoriesCount === 0}
          >
            {classifyingRoles ? "Classifying…" : "Classify Roles"}
          </Button>
        )}
      </div>
      {activeRoleCategoriesCount === 0 && company.contacts.length > 0 && (
        <p className="mb-3 text-sm text-muted-foreground">
          No active role categories yet —{" "}
          <Link to="/role-categories/new" className="text-primary-text hover:underline">
            add one
          </Link>{" "}
          before classifying roles.
        </p>
      )}
      {classifyRolesError && (
        <p className="mb-3 text-sm text-destructive">{classifyRolesError}</p>
      )}
      {roleRelevanceError && (
        <p className="mb-3 text-sm text-destructive">{roleRelevanceError}</p>
      )}
      {company.contacts.length === 0 ? (
        <Card>
          <EmptyState
            icon={Users}
            title="No contacts found"
            description="Contacts will appear here once this company has been enriched."
          />
        </Card>
      ) : (
        <TooltipProvider>
          <div className="flex flex-col gap-4">
            {company.contacts.map((contact) => {
              const roleRelevance = roleRelevanceByContact[contact.id];
              return (
                <Card key={contact.id}>
                  <CardHeader>
                    <CardTitle className="flex flex-wrap items-center gap-2 text-base font-bold">
                      {contact.full_name ?? "Unknown"}
                      {contact.role_title && (
                        <span className="font-normal text-muted-foreground">
                          — {contact.role_title}
                        </span>
                      )}
                      {contact.needs_review && (
                        <NeedsReviewBadge reason={contact.needs_review_reason} />
                      )}
                      {roleRelevance && (
                        <Tooltip>
                          <TooltipTrigger className="cursor-default">
                            <RolePriorityBadge
                              priority={roleRelevance.priority}
                              label={roleRelevance.matched_category_name ?? undefined}
                            />
                          </TooltipTrigger>
                          <TooltipContent className="block max-w-sm whitespace-normal text-left">
                            {roleRelevance.reasoning}
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="flex flex-col gap-1 text-sm">
                      {contact.channels.map((channel) => (
                        <li key={channel.id}>
                          {channel.channel_type}: {channel.value}{" "}
                          <span className="text-muted-foreground">
                            ({channel.verification_status})
                          </span>
                        </li>
                      ))}
                    </ul>
                    <ContactOutreachPanel
                      contact={contact}
                      companyId={company.id}
                      products={products ?? []}
                      onContactUpdated={handleOutreachLogged}
                    />
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </TooltipProvider>
      )}

      <h2 className="mb-3 mt-8 text-lg font-bold">Qualification</h2>
      <Card>
        <CardContent>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              onClick={handleCheckQualification}
              disabled={checkingQualification || activeCriteriaCount === 0}
            >
              {checkingQualification ? "Checking…" : "Check Qualification"}
            </Button>
          </div>
          {activeCriteriaCount === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              No active qualification criteria yet —{" "}
              <Link to="/qualification/criteria/new" className="text-primary-text hover:underline">
                add one
              </Link>{" "}
              before checking qualification.
            </p>
          )}
          {checkQualificationError && (
            <p className="mt-3 text-sm text-destructive">{checkQualificationError}</p>
          )}
        </CardContent>
      </Card>

      <div className="mt-4">
        {qualificationResultsError ? (
          <Card>
            <ErrorState message={qualificationResultsError} onRetry={loadQualificationResults} />
          </Card>
        ) : !qualificationResults ? (
          <Card className="p-6">
            <SkeletonLines lines={4} />
          </Card>
        ) : qualificationResults.length === 0 ? (
          <Card>
            <EmptyState
              icon={ClipboardCheck}
              title="No qualification checks yet"
              description="Click Check Qualification above to judge this company against your active criteria."
            />
          </Card>
        ) : (
          <QualificationResultsTable results={qualificationResults} />
        )}
      </div>

      <h2 className="mb-3 mt-8 text-lg font-bold">Recommendations</h2>
      <Card>
        <CardContent>
          <div className="flex flex-wrap items-center gap-3">
            <Select value={selectedProductId} onValueChange={setSelectedProductId}>
              <SelectTrigger className="h-9 min-w-48 bg-card" aria-label="Product">
                <SelectValue placeholder="Select a product…" />
              </SelectTrigger>
              <SelectContent>
                {(products ?? []).map((product) => (
                  <SelectItem key={product.id} value={product.id}>
                    {product.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              onClick={handleGenerateRecommendation}
              disabled={!selectedProductId || generating}
            >
              {generating ? "Generating…" : "Generate Recommendation"}
            </Button>
          </div>
          {products && products.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              No products in the catalog yet —{" "}
              <Link to="/products/new" className="text-primary-text hover:underline">
                add one
              </Link>{" "}
              before generating a recommendation.
            </p>
          )}
          {generateError && <p className="mt-3 text-sm text-destructive">{generateError}</p>}
        </CardContent>
      </Card>

      <div className="mt-4">
        {recommendationsError ? (
          <Card>
            <ErrorState message={recommendationsError} onRetry={loadRecommendations} />
          </Card>
        ) : !recommendations ? (
          <Card className="p-6">
            <SkeletonLines lines={4} />
          </Card>
        ) : recommendations.length === 0 ? (
          <Card>
            <EmptyState
              icon={Lightbulb}
              title="No recommendations yet"
              description="Pick a product above and generate one to see sales-prep talking points for this company."
            />
          </Card>
        ) : (
          <div className="flex flex-col gap-4">
            {recommendations.map((recommendation) => {
              const product = (products ?? []).find((p) => p.id === recommendation.product_id);
              return (
                <Card key={recommendation.id}>
                  <CardHeader>
                    <CardTitle className="text-base font-bold">
                      {product?.name ?? "Recommendation"}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm">{recommendation.pitch_summary}</p>
                    <p className="mt-3 text-sm text-muted-foreground">
                      {recommendation.why_this_company}
                    </p>
                    {recommendation.talking_points.length > 0 && (
                      <ul className="mt-3 list-inside list-disc text-sm">
                        {recommendation.talking_points.map((point, i) => (
                          <li key={i}>{point}</li>
                        ))}
                      </ul>
                    )}
                    <p className="mt-3 text-xs text-muted-foreground">
                      {recommendation.model_used} ·{" "}
                      {new Date(recommendation.created_at).toLocaleString()}
                    </p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
