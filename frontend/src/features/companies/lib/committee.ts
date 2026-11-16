import type { ContactRelevance } from "@/api/types";
import type { Tiering } from "@/features/brief/tiers";

// What the People tab needs to show each person's part in the buying decision on the person's own
// card, so there is one list of people instead of two.
export type CommitteeData = {
  // Each person's part, by contact id (missing when they have not been judged).
  roles: Record<string, ContactRelevance>;
  // The order to list people in: who decides first, then who influences, then who would use it,
  // each by seniority; people not involved or not judged come last.
  orderedIds: string[];
  // The best person to approach first.
  startHereId: string | null;
};

export function committeeFrom(
  contacts: ContactRelevance[],
  tiering: Tiering,
): CommitteeData {
  return {
    roles: Object.fromEntries(contacts.map((c) => [c.contact_id, c])),
    orderedIds: [
      ...tiering.tiers.flatMap((t) => t.people.map((p) => p.contact_id)),
      ...tiering.others.map((p) => p.contact_id),
    ],
    startHereId: tiering.approachFirst,
  };
}

// The company's people in committee order. A person the committee does not know about (added a
// moment ago, say) goes last, in their original order.
export function sortByCommittee<T extends { id: string }>(
  contacts: T[],
  committee: CommitteeData | null,
): T[] {
  if (!committee) return contacts;
  const rank = new Map(committee.orderedIds.map((id, i) => [id, i]));
  const last = committee.orderedIds.length;
  return contacts
    .map((c, i) => ({ c, key: rank.get(c.id) ?? last + i }))
    .sort((a, b) => a.key - b.key)
    .map(({ c }) => c);
}
