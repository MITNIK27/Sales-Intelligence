import { useEffect, useState } from "react";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import { DRAFT_TYPES } from "@/api/types";
import type { Contact, Draft, DraftGenerateRequest, DraftType, DraftUpdateRequest, Product } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const DRAFT_TYPE_LABELS: Record<DraftType, string> = {
  first_touch: "First touch",
  follow_up: "Follow-up",
};

export function DraftSection({
  contact,
  companyId,
  products,
  onLogAsSent,
}: {
  contact: Contact;
  companyId: string;
  products: Product[];
  onLogAsSent: (draft: Draft) => void;
}) {
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
  const [loggingAsSent, setLoggingAsSent] = useState(false);

  function loadLatestDraft() {
    return apiGet<Draft[]>(`/companies/${companyId}/drafts?contact_id=${contact.id}`)
      .then((drafts) => {
        const active = drafts.find((d) => d.status === "draft") ?? null;
        setDraft(active);
        setSubject(active?.subject ?? "");
        setBody(active?.body ?? "");
      })
      .catch(() => {
        // Supplementary — a failure here shouldn't block generating a new draft.
      });
  }

  useEffect(() => {
    loadLatestDraft();
  }, [contact.id]);

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
      const generated = await apiPost<Draft>(`/companies/${companyId}/drafts`, payload);
      setDraft(generated);
      setSubject(generated.subject ?? "");
      setBody(generated.body);
      setSaved(false);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "failed to generate draft");
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
      setGenerateError(err instanceof Error ? err.message : "failed to save edits");
    } finally {
      setSaving(false);
    }
  }

  async function handleLogAsSent() {
    setLoggingAsSent(true);
    setGenerateError(null);
    try {
      // Persist any pending edits first -- the OutreachActivity this creates references the
      // draft by id, so the draft row itself must reflect the final text before it's marked sent.
      const saved = await saveEdits();
      if (saved) onLogAsSent(saved);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "failed to save edits before send");
    } finally {
      setLoggingAsSent(false);
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
      setGenerateError(err instanceof Error ? err.message : "failed to discard draft");
    } finally {
      setDiscarding(false);
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={selectedProductId} onValueChange={setSelectedProductId}>
          <SelectTrigger className="h-9 min-w-40 bg-card" aria-label="Product">
            <SelectValue placeholder="Select a product…" />
          </SelectTrigger>
          <SelectContent>
            {products.map((product) => (
              <SelectItem key={product.id} value={product.id}>
                {product.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={draftType} onValueChange={(v) => setDraftType(v as DraftType)}>
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
          disabled={!selectedProductId || generating}
          size="sm"
          className="h-9"
        >
          {generating ? "Generating…" : "Generate Draft"}
        </Button>
      </div>
      {generateError && <p className="text-sm text-destructive">{generateError}</p>}

      {draft && (
        <div className="flex flex-col gap-2 rounded-md border border-border p-3">
          <p className="text-xs text-muted-foreground">
            {DRAFT_TYPE_LABELS[draft.draft_type]} draft — {draft.model_used} · review and edit
            before sending.
          </p>
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
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" onClick={handleSaveEdits} disabled={saving}>
              {saving ? "Saving…" : "Save edits"}
            </Button>
            <Button type="button" size="sm" onClick={handleLogAsSent} disabled={loggingAsSent}>
              {loggingAsSent ? "Preparing…" : "Log as Sent"}
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
        </div>
      )}
    </div>
  );
}
