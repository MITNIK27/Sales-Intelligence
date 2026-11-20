import {
  Navigate,
  Route,
  Routes,
  useParams,
  useSearchParams,
} from "react-router-dom";

import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { CompaniesListPage } from "@/features/companies/CompaniesListPage";
import { CompanyDetailPage } from "@/features/companies/CompanyDetailPage";
import { OutreachPage } from "@/features/outreach/OutreachPage";
import { DocumentsPage } from "@/features/documents/DocumentsPage";
import { MarketDiscoveryPage } from "@/features/enrichment/MarketDiscoveryPage";
import { UploadPage } from "@/features/ingestion/UploadPage";
import { ProductFormPage } from "@/features/products/ProductFormPage";
import { ProductsListPage } from "@/features/products/ProductsListPage";
import { QuickLookPage } from "@/features/quicklook/QuickLookPage";
import { RoleCategoryFormPage } from "@/features/role_categories/RoleCategoryFormPage";
import { RoleCategoryListPage } from "@/features/role_categories/RoleCategoryListPage";
import { AppLayout } from "@/layout/AppLayout";

// One page serves both views, so an old or shared /searches/:id link lands on the dashboard scoped
// to that search.
function SearchRedirect() {
  const { runId } = useParams();
  return <Navigate to={`/?search=${runId ?? ""}`} replace />;
}

// The old Drafts and Follow-ups addresses now live in Outreach; the rest of the address is kept.
function ToOutreach({ view }: { view: "drafts" | "follow-ups" }) {
  const [params] = useSearchParams();
  const next = new URLSearchParams(params);
  next.set("view", view);
  return <Navigate to={`/outreach?${next.toString()}`} replace />;
}

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/searches/:runId" element={<SearchRedirect />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/companies" element={<CompaniesListPage />} />
        <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
        <Route path="/outreach" element={<OutreachPage />} />
        <Route path="/drafts" element={<ToOutreach view="drafts" />} />
        <Route path="/follow-ups" element={<ToOutreach view="follow-ups" />} />
        <Route path="/market-discovery" element={<MarketDiscoveryPage />} />
        <Route path="/products" element={<ProductsListPage />} />
        <Route path="/products/new" element={<ProductFormPage />} />
        <Route path="/products/:productId/edit" element={<ProductFormPage />} />
        <Route path="/qualification/check" element={<QuickLookPage />} />
        <Route path="/role-categories" element={<RoleCategoryListPage />} />
        <Route path="/role-categories/new" element={<RoleCategoryFormPage />} />
        <Route
          path="/role-categories/:roleCategoryId/edit"
          element={<RoleCategoryFormPage />}
        />
      </Route>
    </Routes>
  );
}
