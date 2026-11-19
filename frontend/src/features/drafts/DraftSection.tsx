import { useEffect, useState } from "react";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import { DRAFT_TYPES } from "@/api/types";
import type {
  Contact,
  Draft,
  DraftGenerateRequest,
  DraftType,
  DraftUpdateRequest,
  LogOutreachActivityResponse,
  Product,
} from "@/api/types";
import { Link } from "react-router-dom";

import { OfferingSearchPicker } from "@/components/OfferingSearchPicker";
import {
  DRAFT_SOURCE_HEADING,
  isBestFit,
  recommendedOffering,
  type DraftOffering,
} from "@/features/companies/lib/draftOfferings";
import {
  DRAFT_TYPE_LABELS,
  suggestedDraftType,
} from "@/features/drafts/draftTypes";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { DraftAssistant } from "@/features/drafts/DraftAssistant";
import { DraftFlags } from "@/features/drafts/DraftFlags";
import { emailOf } from "@/features/outreach/compose";
import { afterLogLine } from "@/features/outreach/outreachRules";
import { SendFromMail } from "@/features/outreach/SendFromMail";
import { countWords, plural } from "@/lib/format";

// One line under the offering box saying why the chosen offering is on the list.
function pickedReason(
  options: DraftOffering[],
  chosenId: string,
  recommended: string,
): string {
  const chosen = options.find((o) => o.product.id === chosenId);
  if (!chosen)
    return "Not one of the offerings listed for this company: you picked it yourself.";
  if (chosenId === recommended && isBestFit(options, chosenId))
    return "Recommended from the Brief: the best fit for this company.";
  if (chosen.source === "search")
    return `${DRAFT_SOURCE_HEADING.search}: you searched for this one.`;
  if (chosen.source === "brief")
    return `${DRAFT_SOURCE_HEADING.brief}: you made a brief around this one.`;
  return "From the Brief: a fit for this company.";
}

export function DraftSection({
  contact,
  companyId,
  companyNeedsReview,
  products,
  draftOptions,
  reloadKey = 0,
  onActiveDraft,
  onSentLogged,
  onChangeDetails,
}: {
  contact: Contact;
  companyId: string;
  companyNeedsReview: boolean;
  products: Product[];
  // What a draft for this company can be written about: what was searched in Market Discovery, what
  // has a brief of its own, and what the Brief found a strong or possible fit for.
  draftOptions: DraftOffering[];
  // Changes when the draft was logged elsewhere (the log tab), so it is loaded again.
  reloadKey?: number;
  // The draft being worked on, or null; the log tab offers it first.
  onActiveDraft?: (draft: Draft | null) => void;
  // The draft was logged as sent from here; the contact as it is now.
  onSentLogged: (contact: Contact) => void;
  // Open the log tab, to set the date or add a note before logging.
  onChangeDetails: () => void;
}) {
  const blockedByReview = companyNeedsReview || contact.needs_review;
  const [selectedProductId, setSelectedProductId] = useState("");
  const [draftType, setDraftType] = useState<DraftType>("first_touch");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const [draft, setDraft] = useState<Draft | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [loggingSent, setLoggingSent] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sentNote, setSentNote] = useState<string | null>(null);

  function loadLatestDraft() {
    return apiGet<Draft[]>(
      `/companies/${companyId}/drafts?contact_id=${contact.id}`,
    )
      .then((drafts) => {
        const active = drafts.find((d) => d.status === "draft") ?? null;
        setDraft(active);
        setSubject(active?.subject ?? "");
        setBody(active?.body ?? "");
        // Start on the email that comes next, from how many were already sent to this person.
        setDraftType(
          suggestedDraftType(drafts.filter((d) => d.status === "sent").length),
        );
      })
      .catch(() => {
        // Supplementary — a failure here shouldn't block generating a new draft.
      });
  }

  useEffect(() => {
    loadLatestDraft();
  }, [contact.id, reloadKey]);

  useEffect(() => {
    onActiveDraft?.(draft);
  }, [draft, onActiveDraft]);

  // Start on the best strong or possible fit; with none, on the first thing the rep searched or
  // made a brief around.
  const recommended = recommendedOffering(draftOptions);
  useEffect(() => {
    if (recommended) setSelectedProductId((current) => current || recommended);
  }, [recommended]);

  async function handleGenerate() {
    if (!selectedProductId) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const payload: DraftGenerateRequest = {
        contact_id: contact.id,
        product_id: selectedProductId,
        draft_type: draftType,
      };
      const generated = await apiPost<Draft>(
        `/companies/${companyId}/drafts`,
        payload,
      );
      setDraft(generated);
      setSubject(generated.subject ?? "");
      setBody(generated.body);
      setSaved(false);
    } catch (err) {
      setGenerateError(
        err instanceof Error ? err.message : "failed to generate draft",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function saveEdits(): Promise<Draft | null> {
    if (!draft) return null;
    const update: DraftUpdateRequest = { subject, body };
    const updated = await apiPatch<Draft>(`/drafts/${draft.id}`, update);
    setDraft(updated);
    return updated;
  }

  async function handleSaveEdits() {
    setSaving(true);
    setSaved(false);
    try {
      await saveEdits();
      setSaved(true);
    } catch (err) {
      setGenerateError(
        err instanceof Error ? err.message : "failed to save edits",
      );
    } finally {
      setSaving(false);
    }
  }

  // The rep says they sent it. Pending edits are saved first, because the log points at this
  // draft and the draft must hold the text that was really sent.
  async function handleConfirmSent() {
    if (!draft) return;
    setLoggingSent(true);
    setSendError(null);
    try {
      await saveEdits();
      const response = await apiPost<LogOutreachActivityResponse>(
        `/contacts/${contact.id}/outreach-activities`,
        { channel: "email", activity_type: "sent", draft_id: draft.id },
      );
      setDraft(null);
      setSubject("");
      setBody("");
      setSentNote(afterLogLine(response.contact));
      onSentLogged(response.contact);
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "could not log it");
    } finally {
      setLoggingSent(false);
    }
  }

  async function handleDiscard() {
    if (!draft) return;
    setDiscarding(true);
    try {
      await apiPost<Draft>(`/drafts/${draft.id}/discard`);
      setDraft(null);
      setSubject("");
      setBody("");
    } catch (err) {
      setGenerateError(
        err instanceof Error ? err.message : "failed to discard draft",
      );
    } finally {
      setDiscarding(false);
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3">
      {blockedByReview && !draft && !contact.needs_review && (
        <p className="border-l-2 border-chip-warning-fg pl-3 text-sm text-chip-warning-fg">
          Confirm the flagged company first, then you can generate a draft.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <OfferingSearchPicker
          products={products}
          options={draftOptions}
          value={selectedProductId}
          onChange={setSelectedProductId}
          className="min-w-56"
        />
        <Select
          value={draftType}
          onValueChange={(v) => setDraftType(v as DraftType)}
        >
          <SelectTrigger className="h-9 bg-card" aria-label="Draft type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DRAFT_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {DRAFT_TYPE_LABELS[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          onClick={handleGenerate}
          disabled={!selectedProductId || generating || blockedByReview}
          title={
            blockedByReview
              ? "Confirm the flagged company/contact before drafting"
              : undefined
          }
          size="sm"
          className="h-9"
        >
          {generating ? "Generating…" : "Generate Draft"}
        </Button>
      </div>
      {draftOptions.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          {pickedReason(draftOptions, selectedProductId, recommended)}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Nothing has been searched, briefed or matched for this company yet.
          Type to search all of our offerings, or{" "}
          <Link
            to={`/companies/${companyId}?tab=opportunity`}
            className="font-medium text-primary-text hover:underline"
          >
            open the Brief
          </Link>{" "}
          to research it.
        </p>
      )}
      {generateError && (
        <p className="text-sm text-destructive">{generateError}</p>
      )}

      {draft && (
        <div className="flex flex-col gap-2 rounded-md border border-border p-3">
          <p className="text-xs text-muted-foreground">
            {DRAFT_TYPE_LABELS[draft.draft_type]} draft — {draft.model_used} ·
            review and edit before sending.
          </p>
          <DraftFlags flags={draft.grounding_flags} />
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            aria-label="Draft subject"
            className="h-9 rounded-md border border-input bg-card px-3 text-sm"
          />
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={6}
            aria-label="Draft body"
          />
          <p className="text-xs text-muted-foreground">
            {countWords(body)} {plural(countWords(body), "word")}
          </p>
          <DraftAssistant
            draftId={draft.id}
            subject={subject}
            body={body}
            initialRevisions={draft.revision_count ?? 0}
            disabled={blockedByReview}
            disabledReason="Confirm this contact first, then you can change the draft."
            onRewritten={(d) => {
              setDraft(d);
              setSubject(d.subject ?? "");
              setBody(d.body);
              setSaved(false);
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              onClick={handleSaveEdits}
              disabled={saving}
            >
              {saving ? "Saving…" : "Save edits"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="destructive"
              onClick={handleDiscard}
              disabled={discarding}
            >
              {discarding ? "Discarding…" : "Discard"}
            </Button>
            {saved && <span className="text-sm text-success">Saved</span>}
          </div>
          <SendFromMail
            to={emailOf(contact)}
            subject={subject}
            body={body}
            busy={loggingSent}
            error={sendError}
            onConfirmSent={() => void handleConfirmSent()}
            onChangeDetails={onChangeDetails}
          />
        </div>
      )}
      {!draft && sentNote && (
        <p role="status" className="text-sm text-success">
          {sentNote}
        </p>
      )}
    </div>
  );
}
