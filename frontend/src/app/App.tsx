import {
  ClipboardCheck,
  Compass,
  ListChecks,
  Package,
  Search,
  Target,
  Upload,
  Users,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";

import { CompaniesListPage } from "@/features/companies/CompaniesListPage";
import { CompanyDetailPage } from "@/features/companies/CompanyDetailPage";
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

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/Skeleton";

type HealthResponse = {
  status: string;
};

const DASHBOARD_TILES = [
  {
    to: "/upload",
    icon: Upload,
    title: "Upload a CSV",
    desc: "Bring in a list of companies/contacts and let it dedupe.",
  },
  {
    to: "/companies",
    icon: Users,
    title: "Companies",
    desc: "Browse everything that's been ingested so far.",
  },
  {
    to: "/follow-ups",
    icon: ListChecks,
    title: "Follow-ups due",
    desc: "Contacts you need to reach out to today or overdue.",
  },
  {
    to: "/needs-review",
    icon: Search,
    title: "Needs review",
    desc: "Scraped matches worth a spot-check — never blocks the pipeline.",
  },
  {
    to: "/market-discovery",
    icon: Compass,
    title: "Market Discovery",
    desc: "Describe a target market and find new companies to enrich.",
  },
  {
    to: "/products",
    icon: Package,
    title: "Products",
    desc: "Manage your catalog so recommendations know what to pitch.",
  },
  {
    to: "/qualification/criteria",
    icon: ClipboardCheck,
    title: "Qualification Criteria",
    desc: "Define what makes a company worth pursuing — judged automatically later.",
  },
  {
    to: "/qualification/check",
    icon: Zap,
    title: "Quick Check",
    desc: "Check whether a company is worth pursuing, right now.",
  },
  {
    to: "/role-categories",
    icon: Target,
    title: "Role Categories",
    desc: "Define which functions matter for outreach — contacts are classified against these.",
  },
];

function HomePage() {
  const [apiStatus, setApiStatus] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/health")
      .then((res) => res.json() as Promise<HealthResponse>)
      .then((data) => setApiStatus(data.status))
      .catch(() => setApiStatus("unreachable"));
  }, []);

  return (
    <div>
      <PageHeader
        eyebrow="Overview"
        title="Sales Intelligence"
        description={
          apiStatus === null ? (
            <Skeleton className="mt-1 h-4 w-40" />
          ) : (
            <>
              API status:{" "}
              <span className={apiStatus === "ok" ? "text-success" : "text-destructive"}>
                {apiStatus}
              </span>
            </>
          )
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {DASHBOARD_TILES.map((tile) => (
          <Link key={tile.to} to={tile.to}>
            <Card className="h-full transition-colors duration-200 hover:border-primary">
              <CardHeader>
                <tile.icon className="size-6 text-primary" />
                <CardTitle className="mt-2">{tile.title}</CardTitle>
                <CardDescription>{tile.desc}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/companies" element={<CompaniesListPage />} />
        <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
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
