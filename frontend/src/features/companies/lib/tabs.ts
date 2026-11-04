export type CompanyTab =
  "overview" | "opportunity" | "people" | "recommendations";

export const COMPANY_TABS: { id: CompanyTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "opportunity", label: "Brief" },
  { id: "people", label: "People" },
  { id: "recommendations", label: "Recommendations" },
];

// The tab named in the address, or Overview when it is missing or not one we have. A link that
// asks for an area or offering opens the Opportunity tab, since that is where they apply.
export function tabFromParams(params: URLSearchParams): CompanyTab {
  const wanted = params.get("tab");
  const known = COMPANY_TABS.find((t) => t.id === wanted);
  if (known) return known.id;
  return params.has("area") ||
    params.has("offerings") ||
    params.has("offering") ||
    params.has("run")
    ? "opportunity"
    : "overview";
}
