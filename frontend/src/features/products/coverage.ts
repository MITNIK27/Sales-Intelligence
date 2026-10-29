import type {
  OfferingCoveragePage,
  OfferingMenuItem,
  OfferingMenuStatus,
  OfferingPageVerdict,
} from "@/api/types";

export const VERDICT_LABEL: Record<OfferingPageVerdict, string> = {
  offering: "Offering",
  not_offering: "Not an offering",
  failed: "Could not read",
};

export const LANE_LABEL: Record<OfferingCoveragePage["lane"], string> = {
  site: "Website page",
  extra: "Added page",
  post: "Blog post",
  menu: "Website menu",
};

export const MENU_STATUS_LABEL: Record<OfferingMenuStatus, string> = {
  covered: "In the catalogue",
  judged_not_offering: "Judged not an offering",
  unreadable: "Could not be read",
  missing: "Not imported",
};

// Statuses a person should look at: everything except what is already covered.
export function needsAttention(item: OfferingMenuItem): boolean {
  return item.status !== "covered";
}

export function menuSummary(menu: OfferingMenuItem[]): { total: number; attention: number } {
  return { total: menu.length, attention: menu.filter(needsAttention).length };
}

// Missing ones first, then unreadable, then "judged not an offering", then the rest.
const ATTENTION_ORDER: OfferingMenuStatus[] = [
  "missing",
  "unreadable",
  "judged_not_offering",
  "covered",
];

export function sortMenu(menu: OfferingMenuItem[]): OfferingMenuItem[] {
  return [...menu].sort(
    (a, b) => ATTENTION_ORDER.indexOf(a.status) - ATTENTION_ORDER.indexOf(b.status),
  );
}

export function filterPages(
  pages: OfferingCoveragePage[],
  query: string,
  verdict: OfferingPageVerdict | "all",
): OfferingCoveragePage[] {
  const needle = query.trim().toLowerCase();
  return pages.filter((page) => {
    if (verdict !== "all" && page.verdict !== verdict) return false;
    if (!needle) return true;
    return (
      page.url.toLowerCase().includes(needle) || (page.title ?? "").toLowerCase().includes(needle)
    );
  });
}

// A page can be put forward as an offering unless it already is one.
export function canTreatAsOffering(page: OfferingCoveragePage): boolean {
  return page.verdict !== "offering" && !page.force_extract;
}

// Blog posts the light first look set aside from their title alone. There are usually hundreds,
// so they are kept apart and the list opens on the pages that matter.
export function isScreenedOut(page: OfferingCoveragePage): boolean {
  return page.lane === "post" && page.verdict === "not_offering";
}

export function splitScreened(pages: OfferingCoveragePage[]): {
  main: OfferingCoveragePage[];
  screened: OfferingCoveragePage[];
} {
  return {
    main: pages.filter((p) => !isScreenedOut(p)),
    screened: pages.filter(isScreenedOut),
  };
}

// The page of a list that is currently showing, with the page number kept in range.
export function pageSlice<T>(items: T[], page: number, pageSize: number): { rows: T[]; page: number } {
  const count = Math.max(1, Math.ceil(items.length / pageSize));
  const current = Math.min(Math.max(1, page), count);
  return { rows: items.slice((current - 1) * pageSize, current * pageSize), page: current };
}
