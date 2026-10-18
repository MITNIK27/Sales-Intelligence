import { ChevronDown } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiGet } from "@/api/client";
import type {
  DashboardOverview,
  DashboardRunList,
  ProductList,
} from "@/api/types";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { ActivityFeed } from "@/features/dashboard/ActivityFeed";
import { AttentionQueue } from "@/features/dashboard/AttentionQueue";
import { CommandBar } from "@/features/dashboard/CommandBar";
import { CostHealth } from "@/features/dashboard/CostHealth";
import { FunnelBars } from "@/features/dashboard/FunnelBars";
import { KpiStrip } from "@/features/dashboard/KpiStrip";
import { Panel } from "@/features/dashboard/parts";
import { RequirementBreakdown } from "@/features/dashboard/RequirementBreakdown";
import { ScopeBar } from "@/features/dashboard/ScopeBar";
import { SearchesTable } from "@/features/dashboard/SearchesTable";
import { SetupChecklist } from "@/features/dashboard/SetupChecklist";
import { TopCompanies } from "@/features/dashboard/TopCompanies";
import { RunWorklist } from "@/features/enrichment/RunWorklist";
import { usePersistentState } from "@/lib/usePersistentState";
import { cn } from "@/lib/utils";

type Period = "7d" | "30d" | "all";

function parsePeriod(value: string | null): Period {
  return value === "7d" || value === "30d" ? value : "all";
}

// The home screen: start a search, see what happened (all searches, or one), and what to do next.
// Read-only — everything shown comes from GET /dashboard/*; the only actions are navigation.
export function DashboardPage() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("search");
  const period = parsePeriod(params.get("period"));

  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<DashboardRunList | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [productId, setProductId] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // Activity and usage are secondary, so they start folded away and remember the choice.
  const [showMore, setShowMore] = usePersistentState(
    "ui.dashboard.more",
    false,
  );

  const loadOverview = useCallback(() => {
    setError(null);
    const query = new URLSearchParams({ period });
    if (runId) query.set("run_id", runId);
    return apiGet<DashboardOverview>(`/dashboard/overview?${query.toString()}`)
      .then((data) => {
        setOverview(data);
        setUpdatedAt(Date.now());
      })
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : "failed to load the dashboard",
        ),
      );
  }, [runId, period]);

  const loadRuns = useCallback(() => {
    if (runId) return Promise.resolve();
    return apiGet<DashboardRunList>(
      `/dashboard/runs?limit=${pageSize}&offset=${(page - 1) * pageSize}&period=${period}`,
    )
      .then(setRuns)
      .catch(() =>
        setRuns({ items: [], total: 0, limit: pageSize, offset: 0 }),
      );
  }, [runId, period, page, pageSize]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  // A running search keeps the numbers moving; poll gently until it ends.
  const running =
    overview?.run?.status === "running" || overview?.run?.status === "pending";
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void loadOverview(), 4000);
    return () => window.clearInterval(timer);
  }, [running, loadOverview]);

  useEffect(() => {
    apiGet<ProductList>("/products")
      .then((list) =>
        setProductId(list.items.length === 1 ? list.items[0].id : null),
      )
      .catch(() => setProductId(null));
  }, []);

  function refresh() {
    setRefreshing(true);
    void Promise.all([loadOverview(), loadRuns()]).finally(() =>
      setRefreshing(false),
    );
  }

  function setScope(nextRun: string | null) {
    const next = new URLSearchParams(params);
    if (nextRun) next.set("search", nextRun);
    else next.delete("search");
    setPage(1);
    setParams(next);
  }

  function setPeriod(next: Period) {
    const query = new URLSearchParams(params);
    if (next === "all") query.delete("period");
    else query.set("period", next);
    setPage(1);
    setParams(query);
  }

  if (error && !overview) {
    return (
      <div>
        <PageHeader title="Dashboard" />
        <ErrorState message={error} onRetry={() => void loadOverview()} />
      </div>
    );
  }

  const searches = overview?.searches ?? [];
  const recent = searches.slice(0, 2).map((s) => s.label);
  const single = runId !== null;

  const funnelPanel = (
    <Panel title="From found to draft">
      <FunnelBars stages={overview?.funnel ?? null} />
    </Panel>
  );

  const searchesPanel = (
    <Panel title="Your searches" flush>
      <SearchesTable
        items={runs?.items ?? null}
        total={runs?.total ?? 0}
        page={page}
        pageSize={pageSize}
        loading={runs === null}
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        onSelect={setScope}
      />
    </Panel>
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      <CommandBar recentSearches={recent} />

      <ScopeBar
        searches={searches}
        runId={runId}
        period={period}
        updatedAt={updatedAt}
        live={running}
        refreshing={refreshing}
        onRunChange={setScope}
        onPeriodChange={setPeriod}
        onRefresh={refresh}
      />
      {/* The numbers below already say this; the sentence stays for screen readers only. */}
      <p className="sr-only" aria-live="polite">
        {overview?.headline}
      </p>

      <KpiStrip
        kpis={overview?.kpis ?? null}
        scope={overview?.scope ?? "all"}
      />

      <SetupChecklist setup={overview?.setup ?? null} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {single ? funnelPanel : searchesPanel}
        <Panel title="Next steps">
          <AttentionQueue items={overview?.attention ?? null} />
        </Panel>
      </div>

      <div
        className={cn(
          "grid grid-cols-1 gap-6 md:grid-cols-2",
          !single && "xl:grid-cols-3",
        )}
      >
        {!single && funnelPanel}
        <Panel title="Requirement results">
          <RequirementBreakdown requirements={overview?.requirements ?? null} />
        </Panel>
        <Panel
          title="Top opportunities"
          footerLink={{ to: "/companies", label: "View all companies" }}
        >
          <TopCompanies companies={overview?.top_companies ?? null} />
        </Panel>
      </div>

      <section aria-label="Activity and usage">
        <button
          type="button"
          onClick={() => setShowMore((open) => !open)}
          aria-expanded={showMore}
          className="flex w-full items-center justify-between gap-3 border border-border bg-card px-5 py-3 text-left text-sm transition-colors duration-200 hover:border-primary focus-visible:outline-2 focus-visible:outline-primary"
        >
          <span className="font-medium">Activity and usage</span>
          <span className="flex items-center gap-3 text-muted-foreground">
            <span className="hidden text-xs sm:inline">
              Read-only view — nothing here changes your data
            </span>
            <ChevronDown
              className={cn(
                "size-4 transition-transform duration-200",
                showMore && "rotate-180",
              )}
              aria-hidden="true"
            />
          </span>
        </button>
        {showMore && (
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Panel title="Recent activity">
              <ActivityFeed events={overview?.activity ?? null} />
            </Panel>
            <Panel title="Cost and health">
              <CostHealth health={overview?.health ?? null} />
            </Panel>
          </div>
        )}
      </section>

      {runId && (
        <div id="results">
          <RunWorklist runId={runId} productId={productId} live={running} />
        </div>
      )}
    </div>
  );
}
