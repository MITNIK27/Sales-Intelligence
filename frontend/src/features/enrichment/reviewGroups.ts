import type { NeedsReviewItem } from "@/api/types";

// Pure helpers behind the Verify Contacts page: group the flat list by company, and turn the rep's
// checkbox selection into the ids the API wants. Kept free of React so they can be tested.

export type ReviewGroup = {
  companyId: string;
  companyName: string;
  companyDomain: string | null;
  // Set when the company itself (not just a person) is unconfirmed, e.g. a guessed website.
  companyFlag: NeedsReviewItem | null;
  contacts: NeedsReviewItem[];
  latestFlaggedAt: string;
};

export const contactKey = (contactId: string) => `contact:${contactId}`;
export const companyKey = (companyId: string) => `company:${companyId}`;

// One group per company, newest activity first; people inside a group are alphabetical so the
// order does not jump around between visits.
export function groupByCompany(items: NeedsReviewItem[]): ReviewGroup[] {
  const groups = new Map<string, ReviewGroup>();
  for (const item of items) {
    let group = groups.get(item.company_id);
    if (!group) {
      group = {
        companyId: item.company_id,
        companyName: item.company_name,
        companyDomain: item.company_domain ?? null,
        companyFlag: null,
        contacts: [],
        latestFlaggedAt: item.flagged_at,
      };
      groups.set(item.company_id, group);
    }
    if (item.entity_type === "company") group.companyFlag = item;
    else if (item.contact_id) group.contacts.push(item);
    if (item.flagged_at > group.latestFlaggedAt)
      group.latestFlaggedAt = item.flagged_at;
  }
  const result = Array.from(groups.values());
  for (const group of result) {
    group.contacts.sort((a, b) =>
      (a.contact_name ?? "").localeCompare(b.contact_name ?? ""),
    );
  }
  return result.sort((a, b) =>
    a.latestFlaggedAt < b.latestFlaggedAt ? 1 : -1,
  );
}

// Every selectable row in a group: its flagged people, and the company itself when flagged.
export function groupKeys(group: ReviewGroup): string[] {
  const keys = group.contacts.map((c) => contactKey(c.contact_id as string));
  if (group.companyFlag) keys.push(companyKey(group.companyId));
  return keys;
}

export type SelectionState = "none" | "some" | "all";

export function selectionState(
  selected: ReadonlySet<string>,
  keys: string[],
): SelectionState {
  if (keys.length === 0) return "none";
  const count = keys.filter((key) => selected.has(key)).length;
  if (count === 0) return "none";
  return count === keys.length ? "all" : "some";
}

// Checking a group (or the master box) selects everything in it unless it is already fully
// selected, in which case it clears it — the usual "select all" toggle.
export function toggleKeys(
  selected: ReadonlySet<string>,
  keys: string[],
): Set<string> {
  const next = new Set(selected);
  const everySelected = keys.length > 0 && keys.every((key) => next.has(key));
  for (const key of keys) {
    if (everySelected) next.delete(key);
    else next.add(key);
  }
  return next;
}

export function splitSelection(selected: ReadonlySet<string>): {
  companyIds: string[];
  contactIds: string[];
} {
  const companyIds: string[] = [];
  const contactIds: string[] = [];
  for (const key of selected) {
    if (key.startsWith("company:"))
      companyIds.push(key.slice("company:".length));
    else if (key.startsWith("contact:"))
      contactIds.push(key.slice("contact:".length));
  }
  return { companyIds, contactIds };
}

// Drop selections whose row no longer exists (confirmed or discarded elsewhere).
export function pruneSelection(
  selected: ReadonlySet<string>,
  groups: ReviewGroup[],
): Set<string> {
  const valid = new Set(groups.flatMap(groupKeys));
  return new Set(Array.from(selected).filter((key) => valid.has(key)));
}
