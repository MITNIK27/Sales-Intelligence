import { useState } from "react";

import type { Contact, Draft, Product } from "@/api/types";
import type { SuggestedOffering } from "@/features/companies/lib/suggestedOfferings";
import { Button } from "@/components/ui/button";
import { ContactTracking } from "@/features/contacts/ContactTracking";
import { DraftSection } from "@/features/drafts/DraftSection";
import {
  LogOutreachActivity,
  type PrefilledDraft,
} from "@/features/outreach/LogOutreachActivity";

type Action = "draft" | "log" | "follow_up";

const ACTIONS: { id: Action; label: string }[] = [
  { id: "draft", label: "Write a draft" },
  { id: "log", label: "Log outreach" },
  { id: "follow_up", label: "Follow-up" },
];

/** Bundles a contact's tracking controls, draft generation (Phase B), and outreach logging
 * (Phase C) — colocated here rather than in CompanyDetailPage because the hand-off between them
 * (an approved draft pre-filling the "Log as Sent" form) is per-contact state that would
 * otherwise have to live in a company-wide map keyed by contact id.
 *
 * The three jobs are three buttons; one opens at a time, so a card is not a wall of form fields.
 * All three stay mounted while closed, so a draft being edited is not lost by looking elsewhere. */
export function ContactOutreachPanel({
  contact,
  companyId,
  companyNeedsReview,
  products,
  researched,
  onContactUpdated,
}: {
  contact: Contact;
  companyId: string;
  companyNeedsReview: boolean;
  products: Product[];
  researched: SuggestedOffering[];
  onContactUpdated: (contact: Contact) => void;
}) {
  const [open, setOpen] = useState<Action | null>(null);
  const [prefilledDraft, setPrefilledDraft] = useState<PrefilledDraft | null>(
    null,
  );

  function handleLogAsSent(draft: Draft) {
    setPrefilledDraft({
      draftId: draft.id,
      channel: draft.channel,
      templateVariant: draft.draft_type,
    });
    setOpen("log");
  }

  return (
    <div>
      <div
        role="group"
        aria-label="Actions for this person"
        className="flex flex-wrap gap-2"
      >
        {ACTIONS.map((a) => (
          <Button
            key={a.id}
            type="button"
            variant="action"
            aria-expanded={open === a.id}
            onClick={() => setOpen(open === a.id ? null : a.id)}
          >
            {a.label}
          </Button>
        ))}
      </div>
      <div hidden={open !== "draft"}>
        <DraftSection
          contact={contact}
          companyId={companyId}
          companyNeedsReview={companyNeedsReview}
          products={products}
          researched={researched}
          onLogAsSent={handleLogAsSent}
        />
      </div>
      <div hidden={open !== "log"}>
        <LogOutreachActivity
          contact={contact}
          onLogged={onContactUpdated}
          prefilledDraft={prefilledDraft}
          onDraftSent={() => setPrefilledDraft(null)}
        />
      </div>
      <div hidden={open !== "follow_up"}>
        <ContactTracking contact={contact} />
      </div>
    </div>
  );
}
