import { useState } from "react";

import type { Contact, Draft, Product } from "@/api/types";
import { ContactTracking } from "@/features/contacts/ContactTracking";
import { DraftSection } from "@/features/drafts/DraftSection";
import { LogOutreachActivity, type PrefilledDraft } from "@/features/outreach/LogOutreachActivity";

/** Bundles a contact's tracking controls, draft generation (Phase B), and outreach logging
 * (Phase C) — colocated here rather than in CompanyDetailPage because the hand-off between them
 * (an approved draft pre-filling the "Log as Sent" form) is per-contact state that would
 * otherwise have to live in a company-wide map keyed by contact id. */
export function ContactOutreachPanel({
  contact,
  companyId,
  products,
  onContactUpdated,
}: {
  contact: Contact;
  companyId: string;
  products: Product[];
  onContactUpdated: (contact: Contact) => void;
}) {
  const [prefilledDraft, setPrefilledDraft] = useState<PrefilledDraft | null>(null);

  function handleLogAsSent(draft: Draft) {
    setPrefilledDraft({
      draftId: draft.id,
      channel: draft.channel,
      templateVariant: draft.draft_type,
    });
  }

  return (
    <>
      <ContactTracking contact={contact} />
      <DraftSection
        contact={contact}
        companyId={companyId}
        products={products}
        onLogAsSent={handleLogAsSent}
      />
      <LogOutreachActivity
        contact={contact}
        onLogged={onContactUpdated}
        prefilledDraft={prefilledDraft}
        onDraftSent={() => setPrefilledDraft(null)}
      />
    </>
  );
}
