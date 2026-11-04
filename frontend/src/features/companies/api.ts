// Every request the company page makes, in one place, so components never build URLs and a path
// change is a one-line edit.
import { apiDelete, apiGet, apiPost, apiPut } from "@/api/client";
import type {
  CompanyConfirmRequest,
  CompanyConfirmResult,
  CompanyDetail,
  Contact,
  Draft,
  JobStatus,
  ProductList,
  CompanyCriterion,
  QualificationResult,
  Recommendation,
  RecommendationGenerateRequest,
  RoleCategoryList,
  RoleRelevanceResult,
  ScrapeJobStarted,
  Signal,
} from "@/api/types";

export const fetchCompany = (id: string) =>
  apiGet<CompanyDetail>(`/companies/${id}`);
export const fetchSignals = (id: string) =>
  apiGet<Signal[]>(`/companies/${id}/signals`);
export const fetchRecommendations = (id: string) =>
  apiGet<Recommendation[]>(`/companies/${id}/recommendations`);
export const fetchProducts = () => apiGet<ProductList>("/products?limit=200");
export const fetchQualificationResults = (id: string) =>
  apiGet<QualificationResult[]>(`/companies/${id}/qualification-results`);
export const fetchRoleRelevance = (id: string) =>
  apiGet<RoleRelevanceResult[]>(`/companies/${id}/role-relevance`);
export const fetchRoleCategories = () =>
  apiGet<RoleCategoryList>("/role-categories");
// Powers the pipeline stepper's "Drafted" step only: the same endpoint each contact's draft
// section calls, without the contact filter.
export const fetchDrafts = (id: string) =>
  apiGet<Draft[]>(`/companies/${id}/drafts`);

export const startScrape = (id: string) =>
  apiPost<ScrapeJobStarted>(`/companies/${id}/scrape`);
export const fetchJob = (jobId: string) => apiGet<JobStatus>(`/jobs/${jobId}`);

export const generateRecommendation = (
  id: string,
  body: RecommendationGenerateRequest,
) => apiPost<Recommendation>(`/companies/${id}/recommendations`, body);
// Checks one company against its own criteria; an informational result, never a Qualified or Not
// qualified label.
export const checkQualification = (id: string) =>
  apiPost<QualificationResult>(`/companies/${id}/qualification-results`);
// Replaces the criteria kept on this company.
export const saveCompanyCriteria = (id: string, criteria: CompanyCriterion[]) =>
  apiPut<CompanyCriterion[]>(`/companies/${id}/criteria`, { criteria });
export const classifyRoles = (id: string) =>
  apiPost<RoleRelevanceResult[]>(`/companies/${id}/role-relevance`);
export const searchContacts = (id: string) =>
  apiPost<Contact[]>(`/companies/${id}/search-contacts`);
export const confirmCompany = (id: string, body: CompanyConfirmRequest) =>
  apiPost<CompanyConfirmResult>(`/companies/${id}/confirm`, body);
export const confirmContact = (contactId: string) =>
  apiPost<Contact>(`/contacts/${contactId}/confirm`);
export const deleteContact = (contactId: string) =>
  apiDelete(`/contacts/${contactId}`);
