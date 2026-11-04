import { useEffect, useState } from "react";

import type {
  CompanyDetail,
  Draft,
  Product,
  QualificationResult,
  Recommendation,
  RoleRelevanceResult,
  Signal,
} from "@/api/types";
import {
  fetchCompany,
  fetchDrafts,
  fetchProducts,
  fetchQualificationResults,
  fetchRecommendations,
  fetchRoleCategories,
  fetchRoleRelevance,
  fetchSignals,
} from "@/features/companies/api";
import {
  errorMessage,
  indexByContact,
} from "@/features/companies/lib/contacts";

// Everything the company page shows, loaded once per company, with a reload function for each
// part. The company itself failing blocks the page; every other part is supplementary, so a
// failure there leaves its section empty (or shows its own error) instead of blanking the page.
export function useCompanyData(companyId: string | undefined) {
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [signalsError, setSignalsError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<
    Recommendation[] | null
  >(null);
  const [recommendationsError, setRecommendationsError] = useState<
    string | null
  >(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [qualificationResults, setQualificationResults] = useState<
    QualificationResult[] | null
  >(null);
  const [qualificationResultsError, setQualificationResultsError] = useState<
    string | null
  >(null);
  const [roleRelevanceByContact, setRoleRelevanceByContact] = useState<
    Record<string, RoleRelevanceResult>
  >({});
  const [roleRelevanceError, setRoleRelevanceError] = useState<string | null>(
    null,
  );
  const [activeRoleCategoriesCount, setActiveRoleCategoriesCount] = useState<
    number | null
  >(null);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);

  function reloadCompany() {
    if (!companyId) return;
    setError(null);
    return fetchCompany(companyId)
      .then(setCompany)
      .catch((err) => setError(errorMessage(err, "failed to load company")));
  }

  // A refresh in the background (while a scrape is running): a failed attempt is ignored, so it
  // never replaces the page with an error; the next one simply tries again.
  function refreshCompany() {
    if (!companyId) return Promise.resolve();
    return fetchCompany(companyId)
      .then(setCompany)
      .catch(() => {});
  }

  function reloadSignals() {
    if (!companyId) return;
    setSignalsError(null);
    return fetchSignals(companyId)
      .then(setSignals)
      .catch((err) =>
        setSignalsError(errorMessage(err, "could not load the signals")),
      );
  }

  function reloadRecommendations() {
    if (!companyId) return;
    setRecommendationsError(null);
    return fetchRecommendations(companyId)
      .then(setRecommendations)
      .catch((err) =>
        setRecommendationsError(
          errorMessage(err, "failed to load recommendations"),
        ),
      );
  }

  function reloadQualificationResults() {
    if (!companyId) return;
    setQualificationResultsError(null);
    return fetchQualificationResults(companyId)
      .then(setQualificationResults)
      .catch((err) =>
        setQualificationResultsError(
          errorMessage(err, "failed to load qualification results"),
        ),
      );
  }

  function reloadRoleRelevance() {
    if (!companyId) return;
    setRoleRelevanceError(null);
    return fetchRoleRelevance(companyId)
      .then((results) => setRoleRelevanceByContact(indexByContact(results)))
      .catch((err) =>
        setRoleRelevanceError(
          errorMessage(err, "failed to load role classifications"),
        ),
      );
  }

  function reloadDrafts() {
    if (!companyId) return;
    return fetchDrafts(companyId)
      .then(setDrafts)
      .catch(() => {
        // Supplementary: a failure here shouldn't block the rest of the page.
      });
  }

  useEffect(() => {
    reloadCompany();
    reloadSignals();
    reloadRecommendations();
    fetchProducts()
      .then((list) => setProducts(list.items))
      .catch(() => {
        // Supplementary: the offering pickers just stay empty.
      });
    reloadQualificationResults();
    reloadRoleRelevance();
    fetchRoleCategories()
      .then((list) =>
        setActiveRoleCategoriesCount(
          list.items.filter((c) => c.is_active).length,
        ),
      )
      .catch(() => {
        // Supplementary.
      });
    reloadDrafts();
  }, [companyId]);

  return {
    company,
    setCompany,
    error,
    setError,
    signals,
    signalsError,
    recommendations,
    setRecommendations,
    recommendationsError,
    products,
    qualificationResults,
    setQualificationResults,
    qualificationResultsError,
    roleRelevanceByContact,
    setRoleRelevanceByContact,
    roleRelevanceError,
    activeRoleCategoriesCount,
    drafts,
    reloadCompany,
    reloadSignals,
    refreshCompany,
    reloadRecommendations,
    reloadQualificationResults,
    reloadRoleRelevance,
    reloadDrafts,
  };
}

export type CompanyData = ReturnType<typeof useCompanyData>;
