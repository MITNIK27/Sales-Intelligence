"""Evidence for an opportunity, with stable provenance. Pure functions, no I/O.

The qualification flow cites evidence by position in a prompt (`S1`..`S10`), which shifts whenever
the evidence list changes, so an old verdict can no longer be audited. Here the model is shown
short labels (`E1`..) only as a convenience for that one prompt; what is stored is the evidence's
own identity: the record id, its address, when it was fetched, a hash of the text it was found
in, and the exact quote. The quote must appear verbatim in that text (checked with the same
`quote_is_in_source` the qualification flow uses), otherwise the citation is not trusted."""

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from app.modules.companies.models import Company
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.qualification.evidence import quote_is_in_source

MAX_EVIDENCE_ITEMS = 25
KIND_COMPANY_FIELD = "company_field"


@dataclass(frozen=True)
class EvidenceItem:
    label: str  # E1, E2.. shown to the model for this one prompt; never stored as the reference
    kind: str  # the signal type (news, job_posting, focus_search...) or "company_field"
    text: str  # what the model sees, and what quotes are checked against
    content_hash: str
    record_id: uuid.UUID | None = None  # set for evidence that is an EnrichmentRecord
    field: str | None = None  # set for a company field (description, industry)
    url: str | None = None
    date: str | None = None
    fetched_at: str | None = None
    source: str | None = None

    @property
    def identity(self) -> str:
        return str(self.record_id) if self.record_id else f"company.{self.field}"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record_text(record: EnrichmentRecord) -> str:
    payload = record.raw_payload or {}
    text = str(payload.get("text", "")).strip()
    summary = str(payload.get("summary") or "").strip()
    return f"{text}. {summary}" if summary and summary not in text else text


def item_from_record(label: str, record: EnrichmentRecord) -> EvidenceItem:
    payload = record.raw_payload or {}
    text = _record_text(record)
    return EvidenceItem(
        label=label,
        kind=str(payload.get("signal_type") or "signal"),
        text=text,
        content_hash=text_hash(text),
        record_id=record.id,
        url=payload.get("url"),
        date=payload.get("date"),
        fetched_at=record.fetched_at.isoformat() if record.fetched_at else None,
        source=record.source,
    )


def build_evidence_pack(company: Company, records: list[EnrichmentRecord]) -> list[EvidenceItem]:
    """The evidence a judgment may use: the company's own description and industry, then the
    stored records (newest first as given), capped so a prompt stays a sensible size. Records with
    no text are skipped. Labels run E1.. in the order returned."""
    candidates: list[tuple[str, dict[str, Any]]] = []
    for field in ("description", "industry"):
        value = getattr(company, field, None)
        if value and str(value).strip():
            candidates.append((field, {"field": field, "text": str(value).strip()}))

    items: list[EvidenceItem] = []
    for field, data in candidates:
        label = f"E{len(items) + 1}"
        items.append(
            EvidenceItem(
                label=label,
                kind=KIND_COMPANY_FIELD,
                text=data["text"],
                content_hash=text_hash(data["text"]),
                field=field,
            )
        )
    for record in records:
        if len(items) >= MAX_EVIDENCE_ITEMS:
            break
        item = item_from_record(f"E{len(items) + 1}", record)
        if item.text:
            items.append(item)
    return items


def evidence_set_hash(items: list[EvidenceItem]) -> str:
    """A fingerprint of everything a judgment was shown: which evidence, and the text of each. The
    same set gives the same hash regardless of order or labels, so it is a safe cache key."""
    parts = sorted(f"{item.identity}:{item.content_hash}" for item in items)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def format_evidence(items: list[EvidenceItem]) -> str:
    if not items:
        return "No evidence is available for this company."
    lines = []
    for item in items:
        when = f", {item.date}" if item.date else ""
        lines.append(f"[{item.label}] ({item.kind}{when}) {item.text}")
    return "\n".join(lines)


def verify_citation(
    items_by_label: dict[str, EvidenceItem], label: str | None, quote: str | None
) -> EvidenceItem | None:
    """The cited item when the label exists and the quote is really in its text; otherwise None."""
    if not label or not quote:
        return None
    item = items_by_label.get(label.strip())
    if item is None or not quote_is_in_source(quote, item.text):
        return None
    return item


def stored_citation(item: EvidenceItem, quote: str) -> dict[str, Any]:
    """The form that is saved: identity and provenance, never the prompt label."""
    return {
        "record_id": str(item.record_id) if item.record_id else None,
        "field": item.field,
        "kind": item.kind,
        "url": item.url,
        "date": item.date,
        "fetched_at": item.fetched_at,
        "content_hash": item.content_hash,
        "quote": quote.strip(),
    }
