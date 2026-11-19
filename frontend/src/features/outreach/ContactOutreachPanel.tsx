import { useState } from "react";

import type { Contact, Draft, Product } from "@/api/types";
import type { DraftOffering } from "@/features/companies/lib/draftOfferings";
import { cn } from "@/lib/utils";
import { DraftSection } from "@/features/drafts/DraftSection";
import { FollowUpPanel } from "@/features/outreach/FollowUpPanel";
import { LogOutreachActivity } from "@/features/outreach/LogOutreachActivity";
import { useOutreachHistory } from "@/features/outreach/useOutreachHistory";

export type OutreachAction = "draft" | "log" | "follow_up";

const ACTIONS: { id: OutreachAction; label: string }[] = [
  { id: "draft", label: "Write a draft" },
  { id: "log", label: "Log outreach" },
  { id: "follow_up", label: "Follow-up" },
];

// The tab named in a link (`?open=draft`), or null for anything else.
export function actionFromParam(value: string | null): OutreachAction | null {
  return ACTIONS.some((a) => a.id === value) ? (value as OutreachAction) : null;
}

/** Bundles a contact's draft, outreach logging and follow-up, colocated here because they share
 * per-contact state: the draft being worked on (the log offers it first, and logging it ends it)
 * and what has been logged (the follow-up tab counts it).
 *
 * The three jobs are three buttons; one opens at a time, so a card is not a wall of form fields.
 * All three stay mounted while closed, so a draft being edited is not lost by looking elsewhere. */
export function ContactOutreachPanel({
  contact,
  companyId,
  companyNeedsReview,
  products,
  draftOptions,
  startOpen = false,
  initialTab = null,
  onContactUpdated,
}: {
  contact: Contact;
  companyId: string;
  companyNeedsReview: boolean;
  products: Product[];
  draftOptions: DraftOffering[];
  // Open on the draft tab when the card first shows (used for the person to start with).
  startOpen?: boolean;
  // Open on this tab when the card first shows (from a link); wins over `startOpen`.
  initialTab?: OutreachAction | null;
  onContactUpdated: (contact: Contact) => void;
}) {
  const [open, setOpen] = useState<OutreachAction | null>(
    initialTab ?? (startOpen ? "draft" : null),
  );
  const [activeDraft, setActiveDraft] = useState<Draft | null>(null);
  // Bumped when the draft was logged from the log tab, so the draft tab reloads and drops it.
  const [draftReload, setDraftReload] = useState(0);
  const [wanted, setWanted] = useState(open === "log" || open === "follow_up");
  const { history, reload } = useOutreachHistory(contact.id, wanted);

  function show(next: OutreachAction | null) {
    setOpen(next);
    if (next === "log" || next === "follow_up") setWanted(true);
  }

  function afterLog(updated: Contact) {
    onContactUpdated(updated);
    void reload();
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label="Actions for this person"
        className="flex flex-wrap gap-x-1 border-b border-border"
      >
        {ACTIONS.map((a) => (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={open === a.id}
            onClick={() => show(open === a.id ? null : a.id)}
            className={cn(
              "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
              open === a.id
                ? "border-ring text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {a.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" hidden={open !== "draft"}>
        <DraftSection
          contact={contact}
          companyId={companyId}
          companyNeedsReview={companyNeedsReview}
          products={products}
          draftOptions={draftOptions}
          reloadKey={draftReload}
          onActiveDraft={setActiveDraft}
          onSentLogged={afterLog}
          onChangeDetails={() => show("log")}
        />
      </div>
      <div role="tabpanel" hidden={open !== "log"}>
        <LogOutreachActivity
          contact={contact}
          draft={activeDraft}
          history={history}
          onLogged={onContactUpdated}
          onHistoryChanged={() => void reload()}
          onDraftLogged={() => setDraftReload((n) => n + 1)}
        />
      </div>
      <div role="tabpanel" hidden={open !== "follow_up"}>
        <FollowUpPanel
          contact={contact}
          history={history}
          onContactUpdated={onContactUpdated}
          onWriteFollowUp={() => show("draft")}
        />
      </div>
    </div>
  );
}
