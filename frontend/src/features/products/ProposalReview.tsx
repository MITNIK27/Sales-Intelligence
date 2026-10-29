import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import { apiPost } from "@/api/client";
import type { OfferingProposal, OfferingProposalChange } from "@/api/types";
import { Checkbox } from "@/components/Checkbox";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { WebsiteLink } from "@/components/WebsiteLink";
import {
  APPROVE_LABEL,
  CHANGE_LABEL,
  groupProposals,
  removalsLabel,
  suggestionsLabel,
  waitingLabel,
} from "@/features/products/proposals";
import { pageSlice } from "@/features/products/coverage";
import { TablePagination } from "@/components/TablePagination";
import { KIND_LABEL } from "@/lib/offerings";
import { cn } from "@/lib/utils";

const CHANGE_STYLE: Record<OfferingProposalChange, string> = {
  new: "bg-chip-success-bg text-chip-success-fg",
  changed: "bg-chip-warning-bg text-chip-warning-fg",
  removed: "bg-chip-rejected-bg text-chip-rejected-fg",
};

// What the website sync found, waiting for a person. Nothing here is live until it is approved.
// Finds from blog posts are kept in their own collapsed list so they never crowd the main one.
export function ProposalReview({
  proposals,
  onDecided,
}: {
  proposals: OfferingProposal[];
  onDecided: () => void;
}) {
  const { main, removals, suggestions } = groupProposals(proposals);
  return (
    <>
      {main.length > 0 && (
        <ProposalCard
          title={waitingLabel(main.length)}
          note="Nothing goes live until you approve it."
          proposals={main}
          onDecided={onDecided}
        />
      )}
      {removals.length > 0 && (
        <ProposalCard
          title={removalsLabel(removals.length)}
          note="These offerings were not found on the website. Archiving hides them from the pickers; Keep leaves them as they are."
          proposals={removals}
          onDecided={onDecided}
          collapsible
        />
      )}
      {suggestions.length > 0 && (
        <ProposalCard
          title={suggestionsLabel(suggestions.length)}
          note="Found in blog posts, so read these carefully. Nothing goes live until you add it."
          proposals={suggestions}
          onDecided={onDecided}
          collapsible
        />
      )}
    </>
  );
}

function ProposalCard({
  title,
  note,
  proposals,
  onDecided,
  collapsible = false,
}: {
  title: string;
  note: string;
  proposals: OfferingProposal[];
  onDecided: () => void;
  collapsible?: boolean;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(!collapsible);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const { rows, page: currentPage } = pageSlice(proposals, page, pageSize);

  const allSelected = proposals.length > 0 && proposals.every((p) => selected.has(p.id));
  const chosen = proposals.filter((p) => selected.has(p.id)).map((p) => p.id);

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function decide(ids: string[], decision: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await apiPost("/products/proposals/decide", { proposal_ids: ids, decision });
      setSelected(new Set());
      onDecided();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not save your decision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6 p-0" aria-label={title}>
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
        {collapsible && (
          <button
            type="button"
            aria-expanded={open}
            aria-label={open ? "Hide this list" : "Show this list"}
            onClick={() => setOpen((v) => !v)}
            className="focus-visible:outline-2 focus-visible:outline-primary"
          >
            {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </button>
        )}
        {open && (
          <Checkbox
            checked={allSelected}
            indeterminate={selected.size > 0}
            onChange={() =>
              setSelected(allSelected ? new Set() : new Set(proposals.map((p) => p.id)))
            }
            label="Select all"
          />
        )}
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">{note}</p>
        {open && (
          <div className="ml-auto flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={busy || chosen.length === 0}
              onClick={() => decide(chosen, "approve")}
            >
              Approve selected ({chosen.length})
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy || chosen.length === 0}
              onClick={() => decide(chosen, "reject")}
            >
              Reject selected
            </Button>
          </div>
        )}
      </div>
      {open && error && <p className="px-5 pt-3 text-sm text-destructive">{error}</p>}
      {open && (
        <ul>
          {rows.map((proposal) => (
            <ProposalRow
              key={proposal.id}
              proposal={proposal}
              checked={selected.has(proposal.id)}
              busy={busy}
              onToggle={() => toggle(proposal.id)}
              onDecide={(decision) => decide([proposal.id], decision)}
            />
          ))}
        </ul>
      )}
      {open && proposals.length > pageSize && (
        <TablePagination
          total={proposals.length}
          page={currentPage}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      )}
    </Card>
  );
}

function ProposalRow({
  proposal,
  checked,
  busy,
  onToggle,
  onDecide,
}: {
  proposal: OfferingProposal;
  checked: boolean;
  busy: boolean;
  onToggle: () => void;
  onDecide: (decision: "approve" | "reject") => void;
}) {
  const before = proposal.current;
  const textChanged =
    proposal.change === "changed" && before !== null && before.description !== proposal.description;
  const flags = proposal.grounding_flags ?? [];
  return (
    <li className="flex items-start gap-3 border-b border-border px-5 py-4 last:border-b-0">
      <div className="pt-1">
        <Checkbox checked={checked} onChange={onToggle} label={`Select ${proposal.name}`} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn("px-2 py-0.5 text-xs font-medium", CHANGE_STYLE[proposal.change])}>
            {CHANGE_LABEL[proposal.change]}
          </span>
          <span className="font-medium">{proposal.name}</span>
          <span className="text-xs text-muted-foreground">{KIND_LABEL[proposal.kind]}</span>
          <WebsiteLink domain={proposal.source_url} className="text-xs" />
          {proposal.possible_duplicate && (
            <span className="bg-chip-warning-bg px-2 py-0.5 text-xs font-medium text-chip-warning-fg">
              Possible duplicate of {proposal.possible_duplicate}
            </span>
          )}
        </div>
        {textChanged && before?.description && (
          <p className="mt-2 text-sm text-muted-foreground line-through decoration-1">
            {before.description}
          </p>
        )}
        <p className="mt-1 text-sm text-muted-foreground">
          {proposal.description ?? "No description."}
        </p>
        {flags.length > 0 && (
          <p className="mt-2 bg-chip-warning-bg px-2 py-1 text-xs text-chip-warning-fg">
            <span className="font-semibold">Check wording: </span>
            {flags.join("; ")}
          </p>
        )}
        {proposal.source_excerpt && (
          <details className="mt-2 text-xs text-muted-foreground">
            <summary className="cursor-pointer text-primary-text hover:underline">
              Compare with the page
            </summary>
            <p className="mt-1 border-l-2 border-border pl-3">{proposal.source_excerpt}…</p>
          </details>
        )}
      </div>
      <div className="flex shrink-0 gap-2">
        <Button type="button" size="sm" disabled={busy} onClick={() => onDecide("approve")}>
          {APPROVE_LABEL[proposal.change]}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => onDecide("reject")}
        >
          {proposal.change === "removed" ? "Keep" : "Skip"}
        </Button>
      </div>
    </li>
  );
}
