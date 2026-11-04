import { Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type {
  CompanyDetail,
  Contact,
  Product,
  ContactRelevance,
  RoleRelevanceResult,
} from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useCompanyFits } from "@/features/companies/hooks/useSuggestedOfferings";
import {
  EVERY_BAND,
  suggestedOfferings,
} from "@/features/companies/lib/suggestedOfferings";
import { ContactCard } from "@/features/companies/sections/ContactCard";
import type { PeopleTools } from "@/features/companies/sections/PeopleCommittee";
import {
  sortByCommittee,
  type CommitteeData,
} from "@/features/companies/lib/committee";

export function ContactsSection({
  company,
  products,
  roleRelevanceByContact,
  buyingRoles,
  committee,
  tools,
  roleRelevanceError,
  activeRoleCategoriesCount,
  onSearch,
  onClassify,
  onConfirmContact,
  onRemoveContact,
  onOutreachLogged,
}: {
  company: CompanyDetail;
  products: Product[] | null;
  roleRelevanceByContact: Record<string, RoleRelevanceResult>;
  // Each person's part in the buying decision, as set in the Brief.
  buyingRoles: Record<string, ContactRelevance>;
  // Set once the people have been ranked: lists them in committee order, each with their part.
  committee: CommitteeData | null;
  // The person-related buttons and notes from the buying-committee ranking, shown in this header.
  tools: PeopleTools;
  roleRelevanceError: string | null;
  activeRoleCategoriesCount: number | null;
  onSearch: () => Promise<void>;
  onClassify: () => Promise<void>;
  onConfirmContact: (contactId: string) => Promise<void>;
  onRemoveContact: (contactId: string) => void;
  onOutreachLogged: (updated: Contact) => void;
}) {
  // What the Brief has researched for this company, best fit first: drafts are written about these.
  const researched = suggestedOfferings(
    useCompanyFits(company.id),
    products ?? [],
    Infinity,
    EVERY_BAND,
  );
  const [searching, setSearching] = useState(false);
  const [classifying, setClassifying] = useState(false);

  async function search() {
    setSearching(true);
    await onSearch();
    setSearching(false);
  }

  async function classify() {
    setClassifying(true);
    await onClassify();
    setClassifying(false);
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">People</h2>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="action"
            onClick={search}
            disabled={searching}
          >
            {searching ? "Searching…" : "Search for Contacts"}
          </Button>
          {company.contacts.length > 0 && (
            <Button
              type="button"
              className="text-sm font-semibold"
              onClick={classify}
              disabled={
                classifying ||
                activeRoleCategoriesCount === 0 ||
                company.needs_review
              }
              title={
                company.needs_review
                  ? "Confirm this company before classifying roles"
                  : undefined
              }
            >
              {classifying ? "Classifying…" : "Classify Roles"}
            </Button>
          )}
        </div>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {tools.actions}
      </div>
      <div className="mb-4 flex flex-col gap-1">{tools.notes}</div>
      {activeRoleCategoriesCount === 0 && company.contacts.length > 0 && (
        <p className="mb-3 text-sm text-muted-foreground">
          No active role categories yet —{" "}
          <Link
            to="/role-categories/new"
            className="text-primary-text hover:underline"
          >
            add one
          </Link>{" "}
          before classifying roles.
        </p>
      )}
      {roleRelevanceError && (
        <p className="mb-3 text-sm text-destructive">{roleRelevanceError}</p>
      )}
      {company.contacts.length === 0 ? (
        <Card>
          <EmptyState
            icon={Users}
            title="No contacts found"
            description="No people have been found yet. Search for contacts above, or use Add a person."
          />
        </Card>
      ) : (
        <TooltipProvider>
          <div className="flex flex-col gap-4">
            {sortByCommittee(company.contacts, committee).map((contact) => (
              <ContactCard
                key={contact.id}
                contact={contact}
                company={company}
                roleRelevance={roleRelevanceByContact[contact.id]}
                buyingRole={buyingRoles[contact.id]}
                committee={
                  committee
                    ? {
                        role: committee.roles[contact.id],
                        startHere: committee.startHereId === contact.id,
                        onOverride: committee.onOverride,
                      }
                    : undefined
                }
                products={products ?? []}
                researched={researched}
                onConfirm={onConfirmContact}
                onRemove={onRemoveContact}
                onOutreachLogged={onOutreachLogged}
              />
            ))}
          </div>
        </TooltipProvider>
      )}
    </>
  );
}
