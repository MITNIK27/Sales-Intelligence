import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { CompaniesListPage } from "@/features/companies/CompaniesListPage";
import { CompanyDetailPage } from "@/features/companies/CompanyDetailPage";
import { DraftsPage } from "@/features/drafts/DraftsPage";
import { FollowUpsPage } from "@/features/contacts/FollowUpsPage";
import { MarketDiscoveryPage } from "@/features/enrichment/MarketDiscoveryPage";
import { NeedsReviewPage } from "@/features/enrichment/NeedsReviewPage";
import { UploadPage } from "@/features/ingestion/UploadPage";
import { ProductFormPage } from "@/features/products/ProductFormPage";
import { ProductsListPage } from "@/features/products/ProductsListPage";
import { AdhocCheckPage } from "@/features/qualification/AdhocCheckPage";
import { CriteriaListPage } from "@/features/qualification/CriteriaListPage";
import { CriterionFormPage } from "@/features/qualification/CriterionFormPage";
import { RoleCategoryFormPage } from "@/features/role_categories/RoleCategoryFormPage";
import { RoleCategoryListPage } from "@/features/role_categories/RoleCategoryListPage";
import { AppLayout } from "@/layout/AppLayout";

// One page serves both views, so an old or shared /searches/:id link lands on the dashboard scoped
// to that search.
function SearchRedirect() {
  const { runId } = useParams();
  return <Navigate to={`/?search=${runId ?? ""}`} replace />;
}

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/searches/:runId" element={<SearchRedirect />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/companies" element={<CompaniesListPage />} />
        <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
        <Route path="/drafts" element={<DraftsPage />} />
        <Route path="/follow-ups" element={<FollowUpsPage />} />
        <Route path="/needs-review" element={<NeedsReviewPage />} />
        <Route path="/market-discovery" element={<MarketDiscoveryPage />} />
        <Route path="/products" element={<ProductsListPage />} />
        <Route path="/products/new" element={<ProductFormPage />} />
        <Route path="/products/:productId/edit" element={<ProductFormPage />} />
        <Route path="/qualification/criteria" element={<CriteriaListPage />} />
        <Route path="/qualification/criteria/new" element={<CriterionFormPage />} />
        <Route
          path="/qualification/criteria/:criterionId/edit"
          element={<CriterionFormPage />}
        />
        <Route path="/qualification/check" element={<AdhocCheckPage />} />
        <Route path="/role-categories" element={<RoleCategoryListPage />} />
        <Route path="/role-categories/new" element={<RoleCategoryFormPage />} />
        <Route path="/role-categories/:roleCategoryId/edit" element={<RoleCategoryFormPage />} />
      </Route>
    </Routes>
  );
}
