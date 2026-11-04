import type { Contact, RoleRelevanceResult } from "@/api/types";

// Pure helpers for the contact list and role classifications, kept out of the components so they
// can be tested and reused.

export function indexByContact(
  results: RoleRelevanceResult[],
  into: Record<string, RoleRelevanceResult> = {},
): Record<string, RoleRelevanceResult> {
  const next = { ...into };
  for (const result of results) next[result.contact_id] = result;
  return next;
}

// Contacts found by a search are merged into the existing list; a contact already there is
// replaced by the fresher copy, never duplicated.
export function mergeContacts(
  existing: Contact[],
  found: Contact[],
): Contact[] {
  const byId = new Map(existing.map((c) => [c.id, c]));
  for (const contact of found) byId.set(contact.id, contact);
  return Array.from(byId.values());
}

export function replaceContact(
  contacts: Contact[],
  updated: Contact,
): Contact[] {
  return contacts.map((c) => (c.id === updated.id ? updated : c));
}

export function removeContact(
  contacts: Contact[],
  contactId: string,
): Contact[] {
  return contacts.filter((c) => c.id !== contactId);
}

export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}
