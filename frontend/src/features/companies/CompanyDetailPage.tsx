import {
  ArrowLeft,
  ClipboardCheck,
  Lightbulb,
  Radar,
  Users,
} from "lucide-react";
import { WebsiteLink } from "@/components/WebsiteLink";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiDelete, apiGet, apiPost } from "@/api/client";
import type {
  CompanyConfirmRequest,
  CompanyConfirmResult,
  CompanyDetail,
  Contact,
  Draft,
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
import { OfferingSelectItems } from "@/components/OfferingSelectItems";
import { ProductMultiSelect } from "@/components/ProductMultiSelect";
import {
  PipelineStatusStepper,
  type PipelineStep,
} from "@/components/PipelineStatusStepper";
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
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useToast } from "@/components/ui/toast";

const POLL_INTERVAL_MS = 1500;

export function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const { showToast } = useToast();
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scrapeJob, setScrapeJob] = useState<JobStatus | null>(null);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<number | null>(null);

  const [recommendations, setRecommendations] = useState<
    Recommendation[] | null
  >(null);
  const [recommendationsError, setRecommendationsError] = useState<
    string | null
  >(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  // Two separate selections: "Generate Recommendation" below is deliberately single-product (a
  // rep picks exactly one to research right now), while "Confirm Company" in the header resumes
  // the automated pipeline, which may pitch more than one candidate product per company.
  const [selectedRecommendationProductId, setSelectedRecommendationProductId] =
    useState<string>("");
  const [selectedConfirmProductIds, setSelectedConfirmProductIds] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);

  const [qualificationResults, setQualificationResults] = useState<
    QualificationResult[] | null
  >(null);
  const [qualificationResultsError, setQualificationResultsError] = useState<
    string | null
  >(null);
  const [activeCriteriaCount, setActiveCriteriaCount] = useState<number | null>(
    null,
  );
  const [checkingQualification, setCheckingQualification] = useState(false);

  const [roleRelevanceByContact, setRoleRelevanceByContact] = useState<
    Record<string, RoleRelevanceResult>
  >({});
  const [roleRelevanceError, setRoleRelevanceError] = useState<string | null>(
    null,
  );
  const [activeRoleCategoriesCount, setActiveRoleCategoriesCount] = useState<
    number | null
  >(null);
  const [classifyingRoles, setClassifyingRoles] = useState(false);

  const [searchingContacts, setSearchingContacts] = useState(false);

  const [drafts, setDrafts] = useState<Draft[] | null>(null);

  const [confirmingCompany, setConfirmingCompany] = useState(false);
  const [confirmingContactId, setConfirmingContactId] = useState<string | null>(
    null,
  );

  function loadCompany() {
    if (!companyId) return;
    setError(null);
    return apiGet<CompanyDetail>(`/companies/${companyId}`)
      .then(setCompany)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "failed to load company"),
      );
  }

  function loadSignals() {
    if (!companyId) return;
    return apiGet<Signal[]>(`/companies/${companyId}/signals`)
      .then(setSignals)
      .catch(() => {
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
    return apiGet<ProductList>("/products?limit=200")
      .then((list) => {
        setProducts(list.items);
        // Unambiguous default for the "Confirm Company" multi-select: exactly one product means
        // there's nothing to choose between. The "Generate Recommendation" picker stays unselected
        // either way — that action is deliberately a one-at-a-time, manual research pick.
        if (list.items.length === 1) setSelectedConfirmProductIds([list.items[0].id]);
      })
      .catch(() => {
        // The product select is supplementary — a failure here shouldn't block the rest of the page.
      });
  }

  function loadQualificationResults() {
    if (!companyId) return;
    setQualificationResultsError(null);
    return apiGet<QualificationResult[]>(
      `/companies/${companyId}/qualification-results`,
    )
      .then(setQualificationResults)
      .catch((err) =>
        setQualificationResultsError(
          err instanceof Error
            ? err.message
            : "failed to load qualification results",
        ),
      );
  }

  function loadActiveCriteriaCount() {
    return apiGet<QualificationCriterionList>("/qualification/criteria")
      .then((list) =>
        setActiveCriteriaCount(list.items.filter((c) => c.is_active).length),
      )
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
  }

  function loadRoleRelevanceResults() {
    if (!companyId) return;
    setRoleRelevanceError(null);
    return apiGet<RoleRelevanceResult[]>(
      `/companies/${companyId}/role-relevance`,
    )
      .then((results) => {
        const byContact: Record<string, RoleRelevanceResult> = {};
        for (const result of results) byContact[result.contact_id] = result;
        setRoleRelevanceByContact(byContact);
      })
      .catch((err) =>
        setRoleRelevanceError(
          err instanceof Error
            ? err.message
            : "failed to load role classifications",
        ),
      );
  }

  function loadActiveRoleCategoriesCount() {
    return apiGet<RoleCategoryList>("/role-categories")
      .then((list) =>
        setActiveRoleCategoriesCount(
          list.items.filter((c) => c.is_active).length,
        ),
      )
      .catch(() => {
        // Supplementary — a failure here shouldn't block the rest of the page.
      });
  }

  function loadDrafts() {
    if (!companyId) return;
    // Powers the pipeline stepper's "Drafted" step only — reuses the same endpoint DraftSection
    // calls per-contact, just without the contact_id filter, so no new backend endpoint is needed.
    return apiGet<Draft[]>(`/companies/${companyId}/drafts`)
      .then(setDrafts)
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
    loadDrafts();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [companyId]);

  async function handleGenerateRecommendation() {
    if (!companyId || !selectedRecommendationProductId) return;
    setGenerating(true);
    try {
      const body: RecommendationGenerateRequest = {
        product_id: selectedRecommendationProductId,
      };
      const recommendation = await apiPost<Recommendation>(
        `/companies/${companyId}/recommendations`,
        body,
      );
      setRecommendations((prev) =>
        prev ? [recommendation, ...prev] : [recommendation],
      );
    } catch (err) {
      showToast({
        description:
          err instanceof Error
            ? err.message
            : "failed to generate recommendation",
      });
    } finally {
      setGenerating(false);
    }
  }

  async function handleCheckQualification() {
    if (!companyId) return;
    setCheckingQualification(true);
    try {
      const result = await apiPost<QualificationResult>(
        `/companies/${companyId}/qualification-results`,
      );
      setQualificationResults((prev) => (prev ? [result, ...prev] : [result]));
    } catch (err) {
      showToast({
        description:
          err instanceof Error ? err.message : "failed to check qualification",
      });
    } finally {
      setCheckingQualification(false);
    }
  }

  async function handleClassifyRoles() {
    if (!companyId) return;
    setClassifyingRoles(true);
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
      showToast({
        description:
          err instanceof Error ? err.message : "failed to classify roles",
      });
    } finally {
      setClassifyingRoles(false);
    }
  }

  async function handleSearchContacts() {
    if (!companyId) return;
    setSearchingContacts(true);
    try {
      const found = await apiPost<Contact[]>(
        `/companies/${companyId}/search-contacts`,
      );
      setCompany((prev) => {
        if (!prev) return prev;
        const byId = new Map(prev.contacts.map((c) => [c.id, c]));
        for (const contact of found) byId.set(contact.id, contact);
        return { ...prev, contacts: Array.from(byId.values()) };
      });
    } catch (err) {
      showToast({
        description:
          err instanceof Error ? err.message : "failed to search for contacts",
      });
    } finally {
      setSearchingContacts(false);
    }
  }

  async function handleDeleteContact(contactId: string) {
    try {
      await apiDelete(`/contacts/${contactId}`);
      setCompany((prev) =>
        prev
          ? {
              ...prev,
              contacts: prev.contacts.filter((c) => c.id !== contactId),
            }
          : prev,
      );
    } catch (err) {
      showToast({
        description:
          err instanceof Error ? err.message : "failed to remove contact",
      });
    }
  }

  async function handleConfirmCompany() {
    if (!companyId) return;
    setConfirmingCompany(true);
    try {
      const body: CompanyConfirmRequest = {
        product_ids: selectedConfirmProductIds,
      };
      const result = await apiPost<CompanyConfirmResult>(
        `/companies/${companyId}/confirm`,
        body,
      );
      setCompany(result.company);
      await Promise.all([loadRoleRelevanceResults(), loadDrafts()]);
    } catch (err) {
      showToast({
        description:
          err instanceof Error ? err.message : "failed to confirm company",
      });
    } finally {
      setConfirmingCompany(false);
    }
  }

  async function handleConfirmContact(contactId: string) {
    setConfirmingContactId(contactId);
    try {
      const updatedContact = await apiPost<Contact>(
        `/contacts/${contactId}/confirm`,
      );
      setCompany((prev) =>
        prev
          ? {
              ...prev,
              contacts: prev.contacts.map((c) =>
                c.id === updatedContact.id ? updatedContact : c,
              ),
            }
          : prev,
      );
    } catch (err) {
      showToast({
        description:
          err instanceof Error ? err.message : "failed to confirm contact",
      });
    } finally {
      setConfirmingContactId(null);
    }
  }

  function handleOutreachLogged(updatedContact: Contact) {
    setCompany((prev) =>
      prev
        ? {
            ...prev,
            contacts: prev.contacts.map((c) =>
              c.id === updatedContact.id ? updatedContact : c,
            ),
          }
        : prev,
    );
    loadDrafts();
  }

  async function handleScrape() {
    if (!companyId) return;
    setTriggering(true);
    setScrapeJob(null);
    try {
      const started = await apiPost<ScrapeJobStarted>(
        `/companies/${companyId}/scrape`,
      );
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

  const latestQualification = qualificationResults?.[0] ?? null;
  const rolesClassifiedCount = Object.keys(roleRelevanceByContact).length;
  const draftsGeneratedCount = (drafts ?? []).length;

  const pipelineSteps: PipelineStep[] = [
    { label: "Discovered", status: "done" },
    {
      label: "Enriched",
      status:
        company.enrichment_status === "enriched"
          ? "done"
          : company.enrichment_status === "pending"
            ? "in_progress"
            : company.enrichment_status === "failed"
              ? "attention"
              : "pending",
      detail:
        company.enrichment_status === "enriched"
          ? "Website scraped for details, signals, and contacts"
          : company.enrichment_status === "pending"
            ? "Scraping now…"
            : company.enrichment_status === "failed"
              ? (company.enrichment_error ?? "Scrape failed")
              : "Not scraped yet",
    },
    {
      label: "Qualified",
      status: latestQualification ? "done" : "pending",
      detail: latestQualification
        ? `Verdict: ${latestQualification.overall_verdict.replace(/_/g, " ")}`
        : activeCriteriaCount === 0
          ? "No active qualification criteria configured"
          : "Not checked yet",
    },
    {
      label: "Roles classified",
      status: rolesClassifiedCount > 0 ? "done" : "pending",
      detail:
        rolesClassifiedCount > 0
          ? `${rolesClassifiedCount} contact(s) classified`
          : company.contacts.length === 0
            ? "No contacts yet to classify"
            : "Not classified yet",
    },
    {
      label: "Drafted",
      status: draftsGeneratedCount > 0 ? "done" : "pending",
      detail:
        draftsGeneratedCount > 0
          ? `${draftsGeneratedCount} draft(s) generated`
          : "No drafts generated yet",
    },
  ];

  return (
    <div>
      {backLink}
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2">
            {company.name}
            {company.needs_review && (
              <NeedsReviewBadge reason={company.needs_review_reason} />
            )}
          </span>
        }
        action={
          company.needs_review ? (
            <div className="flex flex-col items-end gap-2">
              {products && products.length > 1 && (
                <ProductMultiSelect
                  products={products}
                  selectedIds={new Set(selectedConfirmProductIds)}
                  onToggle={(productId) =>
                    setSelectedConfirmProductIds((current) =>
                      current.includes(productId)
                        ? current.filter((id) => id !== productId)
                        : [...current, productId],
                    )
                  }
                />
              )}
              <Button
                type="button"
                size="sm"
                onClick={handleConfirmCompany}
                disabled={confirmingCompany}
              >
                {confirmingCompany ? "Confirming…" : "Confirm Company"}
              </Button>
            </div>
          ) : undefined
        }
      />

      <div className="mb-6">
        <PipelineStatusStepper steps={pipelineSteps} />
      </div>

      <Card>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Website</dt>
            <dd>
              {company.domain ? <WebsiteLink domain={company.domain} /> : "—"}
            </dd>
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
                  last enriched{" "}
                  {new Date(company.last_enriched_at).toLocaleString()}
                </span>
              )}
            </div>
            <Button
              type="button"
              onClick={handleScrape}
              disabled={scrapeInFlight}
            >
              {scrapeInFlight
                ? "Scraping…"
                : company.enrichment_status === "never_enriched"
                  ? "Scrape"
                  : "Re-scrape"}
            </Button>
          </div>
          {company.enrichment_status === "failed" &&
            company.enrichment_error && (
              <p className="mt-3 text-sm text-destructive">
                {company.enrichment_error}
              </p>
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
            description={
              company.enrichment_status === "never_enriched"
                ? "Not scraped yet — click Scrape above to search for news mentions and hiring signals."
                : company.enrichment_status === "enriched" &&
                    company.last_enriched_at
                  ? `Scraped on ${new Date(company.last_enriched_at).toLocaleDateString()} — no news mentions or hiring signals found this time.`
                  : "News mentions and hiring signals will appear here once found."
            }
          />
        ) : (
          <ul className="divide-y divide-border">
            {signals.map((signal, i) => (
              <li
                key={i}
                className="flex flex-wrap items-center gap-2 px-4 py-3"
              >
                <SignalTypeBadge type={signal.signal_type} />
                <span className="text-sm">{signal.text}</span>
                {signal.date && (
                  <span className="text-sm text-muted-foreground">
                    — {signal.date}
                  </span>
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

      <h2 className="mb-3 mt-8 text-lg font-bold">Qualification</h2>
      <p className="mb-3 text-sm text-muted-foreground">
        A company-level gate checked against your active criteria — whether this
        is worth pursuing at all, before deciding who to contact there.
      </p>
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
              <Link
                to="/qualification/criteria/new"
                className="text-primary-text hover:underline"
              >
                add one
              </Link>{" "}
              before checking qualification.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="mt-4">
        {qualificationResultsError ? (
          <Card>
            <ErrorState
              message={qualificationResultsError}
              onRetry={loadQualificationResults}
            />
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

      <div className="mb-3 mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">Contacts</h2>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={handleSearchContacts}
            disabled={searchingContacts}
          >
            {searchingContacts ? "Searching…" : "Search for Contacts"}
          </Button>
          {company.contacts.length > 0 && (
            <Button
              type="button"
              size="sm"
              onClick={handleClassifyRoles}
              disabled={
                classifyingRoles ||
                activeRoleCategoriesCount === 0 ||
                company.needs_review
              }
              title={
                company.needs_review
                  ? "Confirm this company before classifying roles"
                  : undefined
              }
            >
              {classifyingRoles ? "Classifying…" : "Classify Roles"}
            </Button>
          )}
        </div>
      </div>
      <p className="mb-3 text-sm text-muted-foreground">
        "Search for Contacts" searches public web results for likely LinkedIn
        profile mentions — it does not log into LinkedIn or require your
        account, and every match is flagged for review since it's a
        low-confidence heuristic.
      </p>
      {activeRoleCategoriesCount === 0 && company.contacts.length > 0 && (
        <p className="mb-3 text-sm text-muted-foreground">
          No active role categories yet —{" "}
          <Link
            to="/role-categories/new"
            className="text-primary-text hover:underline"
          >
            add one
          </Link>{" "}
          before classifying roles.
        </p>
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
                  <CardHeader className="flex flex-row items-start justify-between gap-3">
                    <CardTitle className="flex flex-wrap items-center gap-2 text-base font-bold">
                      {contact.full_name ?? "Unknown"}
                      {contact.role_title && (
                        <span className="font-normal text-muted-foreground">
                          — {contact.role_title}
                        </span>
                      )}
                      {contact.needs_review && (
                        <>
                          <NeedsReviewBadge
                            reason={contact.needs_review_reason}
                          />
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => handleConfirmContact(contact.id)}
                            disabled={confirmingContactId === contact.id}
                          >
                            {confirmingContactId === contact.id
                              ? "Confirming…"
                              : "Confirm Contact"}
                          </Button>
                        </>
                      )}
                      {roleRelevance && (
                        <Tooltip>
                          <TooltipTrigger className="cursor-default">
                            <RolePriorityBadge
                              priority={roleRelevance.priority}
                              label={
                                roleRelevance.matched_category_name ?? undefined
                              }
                            />
                          </TooltipTrigger>
                          <TooltipContent className="block max-w-sm whitespace-normal text-left">
                            {roleRelevance.reasoning}
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </CardTitle>
                    <button
                      type="button"
                      onClick={() => {
                        if (
                          window.confirm(
                            `Remove ${contact.full_name ?? "this contact"}?`,
                          )
                        ) {
                          handleDeleteContact(contact.id);
                        }
                      }}
                      className="shrink-0 text-sm text-muted-foreground hover:text-destructive hover:underline"
                    >
                      Remove
                    </button>
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
                      companyNeedsReview={company.needs_review}
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

      <h2 className="mb-3 mt-8 text-lg font-bold">Recommendations</h2>
      <Card>
        <CardContent>
          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={selectedRecommendationProductId}
              onValueChange={setSelectedRecommendationProductId}
            >
              <SelectTrigger
                className="h-9 min-w-48 bg-card"
                aria-label="Offering"
              >
                <SelectValue placeholder="Select an offering…" />
              </SelectTrigger>
              <SelectContent>
                <OfferingSelectItems products={products ?? []} />
              </SelectContent>
            </Select>
            <Button
              type="button"
              onClick={handleGenerateRecommendation}
              disabled={!selectedRecommendationProductId || generating}
            >
              {generating ? "Generating…" : "Generate Recommendation"}
            </Button>
          </div>
          {products && products.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              No offerings added yet —{" "}
              <Link
                to="/products/new"
                className="text-primary-text hover:underline"
              >
                add one
              </Link>{" "}
              before generating a recommendation.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="mt-4">
        {recommendationsError ? (
          <Card>
            <ErrorState
              message={recommendationsError}
              onRetry={loadRecommendations}
            />
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
              description="Pick an offering above and generate one to see sales-prep talking points for this company."
            />
          </Card>
        ) : (
          <div className="flex flex-col gap-4">
            {recommendations.map((recommendation) => {
              const product = (products ?? []).find(
                (p) => p.id === recommendation.product_id,
              );
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
