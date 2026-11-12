import { confirmNotes } from "@/features/companies/lib/confirmNotes";
import type { CompanyCriterion, Contact } from "@/api/types";
import { useToast } from "@/components/ui/toast";
import {
  checkQualification,
  classifyRoles,
  confirmCompany,
  confirmContact,
  deleteContact,
  generateRecommendation,
  restoreCompany,
  saveCompanyCriteria,
  searchContacts,
} from "@/features/companies/api";
import type { CompanyData } from "@/features/companies/hooks/useCompanyData";
import {
  errorMessage,
  indexByContact,
  mergeContacts,
  removeContact,
  replaceContact,
} from "@/features/companies/lib/contacts";

// The things a rep can do on the company page. Each one updates the page's data when it succeeds
// and shows a toast when it fails; none of them throws, so a component can simply await it and
// then clear its own busy state.
export function useCompanyActions(
  companyId: string | undefined,
  data: CompanyData,
) {
  const { showToast } = useToast();
  const fail = (err: unknown, fallback: string) =>
    showToast({ description: errorMessage(err, fallback) });

  // Undo "not a fit": the company is listed and used by automatic work again.
  async function restore() {
    if (!companyId) return;
    try {
      await restoreCompany(companyId);
      await data.refreshCompany();
      showToast({ description: "Company restored.", variant: "success" });
    } catch (err) {
      fail(err, "failed to restore the company");
    }
  }

  async function createRecommendation(productId: string) {
    if (!companyId) return;
    try {
      const recommendation = await generateRecommendation(companyId, {
        product_id: productId,
      });
      data.setRecommendations((prev) =>
        prev ? [recommendation, ...prev] : [recommendation],
      );
    } catch (err) {
      fail(err, "failed to generate recommendation");
    }
  }

  async function saveCriteria(criteria: CompanyCriterion[]) {
    if (!companyId) return;
    try {
      await saveCompanyCriteria(companyId, criteria);
      data.reloadCompany();
    } catch (err) {
      fail(err, "failed to save the criteria");
    }
  }

  async function runQualification() {
    if (!companyId) return;
    try {
      const result = await checkQualification(companyId);
      data.setQualificationResults((prev) =>
        prev ? [result, ...prev] : [result],
      );
    } catch (err) {
      fail(err, "failed to check qualification");
    }
  }

  async function runRoleClassification() {
    if (!companyId) return;
    try {
      const results = await classifyRoles(companyId);
      data.setRoleRelevanceByContact((prev) => indexByContact(results, prev));
    } catch (err) {
      fail(err, "failed to classify roles");
    }
  }

  async function findContacts() {
    if (!companyId) return;
    try {
      const found = await searchContacts(companyId);
      data.setCompany((prev) =>
        prev
          ? { ...prev, contacts: mergeContacts(prev.contacts, found) }
          : prev,
      );
      showToast({
        description:
          found.length === 0
            ? "The search found no people. Public search results do not list everyone; add someone you know from the Brief tab."
            : `Found ${found.length} ${found.length === 1 ? "person" : "people"}.`,
      });
    } catch (err) {
      fail(err, "failed to search for contacts");
    }
  }

  async function removeOneContact(contactId: string) {
    try {
      await deleteContact(contactId);
      data.setCompany((prev) =>
        prev
          ? { ...prev, contacts: removeContact(prev.contacts, contactId) }
          : prev,
      );
    } catch (err) {
      fail(err, "failed to remove contact");
    }
  }

  async function confirmWholeCompany(productIds: string[]) {
    if (!companyId) return;
    try {
      const result = await confirmCompany(companyId, {
        product_ids: productIds,
      });
      data.setCompany(result.company);
      await Promise.all([data.reloadRoleRelevance(), data.reloadDrafts()]);
      const notes = confirmNotes(result);
      showToast({
        description:
          notes.length > 0
            ? `Company confirmed. ${notes.join(" ")}`
            : "Company confirmed.",
      });
    } catch (err) {
      fail(err, "failed to confirm company");
    }
  }

  async function confirmOneContact(contactId: string) {
    try {
      const updated = await confirmContact(contactId);
      data.setCompany((prev) =>
        prev
          ? { ...prev, contacts: replaceContact(prev.contacts, updated) }
          : prev,
      );
    } catch (err) {
      fail(err, "failed to confirm contact");
    }
  }

  function outreachLogged(updated: Contact) {
    data.setCompany((prev) =>
      prev
        ? { ...prev, contacts: replaceContact(prev.contacts, updated) }
        : prev,
    );
    data.reloadDrafts();
  }

  return {
    restore,
    createRecommendation,
    runQualification,
    saveCriteria,
    runRoleClassification,
    findContacts,
    removeOneContact,
    confirmWholeCompany,
    confirmOneContact,
    outreachLogged,
  };
}

export type CompanyActions = ReturnType<typeof useCompanyActions>;
