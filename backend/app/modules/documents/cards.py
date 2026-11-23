"""Summaries and knowledge cards for a document, written by Gemini after the document is read.

A background job, separate from reading: reading must never fail because a model quota ran out, so
the text is saved and searchable first and the summary and cards follow. The job is safe to repeat:
running it again replaces the version's summaries and cards (keeping a person's "hide" on a card
that comes back with the same words), and an hourly check in the worker queues it for any current
version that has none yet, so a quota that ran out mends itself.

The model's answer is never trusted as it is. Code keeps a card only when:
- the passage it names exists, and its quote is found in that passage's text;
- every figure in its statement is in that passage;
- a client name, when given, is written in that passage (otherwise the name is dropped).
Cards from our documents are Gemini only (G1) and the document's text is fenced (G2).

A document tied to offerings may also suggest a better description for them. That is only ever an
offering proposal a person approves; nothing here changes an offering."""

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.documents.card_prompts import (
    CARDS_PROMPT_VERSION,
    CardOut,
    DocumentSummaryOut,
    OfferingUpdateOut,
    SectionOut,
    build_document_summary_prompt,
    build_offering_update_prompt,
    build_section_prompt,
)
from app.modules.documents.embedding import ProgressCallback, queue_embedding
from app.modules.documents.models import (
    AUDIT_SUMMARISE,
    CARD_CLIENT,
    CARD_KINDS,
    CONFIDENCE_LEVELS,
    EVENT_OK,
    EVENT_WARNING,
    STATUS_READY,
    SUMMARY_DOCUMENT,
    SUMMARY_SECTION,
    Document,
    DocumentChunk,
    DocumentOffering,
    DocumentSummary,
    DocumentVersion,
    KnowledgeCard,
)
from app.modules.documents.service import (
    CannotReprocessError,
    _document,
    cards_available,
    record_audit,
    record_event,
)
from app.modules.draft.claims import find_unsupported_claims
from app.modules.jobs.models import STATUS_DONE, STATUS_PENDING, STATUS_RUNNING, Job
from app.modules.jobs.service import enqueue_job
from app.modules.llm.structured import (
    FallbackStructuredLLM,
    LLMError,
    StructuredLLM,
    build_structured_llm,
)
from app.modules.offerings.models import (
    CHANGE_CHANGED,
    LANE_DOCUMENT,
    PROPOSAL_PENDING,
    PROPOSAL_REJECTED,
    OfferingProposal,
)
from app.modules.offerings.names import names_match
from app.modules.products.models import STATUS_ACTIVE, Product
from app.modules.usage.models import ApiUsage

logger = logging.getLogger(__name__)

JOB_TYPE_SUMMARISE_DOCUMENT = "summarise_document"

# After a failed attempt, do not queue another for the same version for this long.
_RETRY_AFTER = timedelta(hours=1)
_MIN_QUOTE_CHARS = 12
_MAX_FACTS_PER_OFFERING = 12
_MAX_DESCRIPTION_CHARS = 700
_MAX_CATALOGUE = 60


# -- what the model may use, and checking what it answered ----------------------------------------


def make_card_llm(settings: Settings) -> StructuredLLM:
    """Gemini only: these prompts carry our documents (G1). A function so a test can swap it."""
    return build_structured_llm(settings, order="gemini")


def _model_of(llm: StructuredLLM) -> str | None:
    if isinstance(llm, FallbackStructuredLLM):
        return llm.last_model
    return getattr(llm, "model", "") or None


_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_DASHES = re.compile(r"[‐-―]")


def _plain(text: str) -> str:
    """Lower case, one space between words, curly quotes and long dashes made plain, so a quote
    copied from a slide still matches when only the typography differs."""
    return " ".join(_DASHES.sub("-", (text or "").translate(_QUOTES)).lower().split())


def quote_is_in(quote: str, passage: str) -> bool:
    """The quote is in the passage. A quote that skips words with "..." matches when each part is
    in the passage."""
    parts = [p.strip(" .") for p in re.split(r"\.\.\.|…", _plain(quote).strip('"'))]
    parts = [p for p in parts if p]
    if not parts or sum(len(p) for p in parts) < _MIN_QUOTE_CHARS:
        return False
    text = _plain(passage)
    return all(part in text for part in parts)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text or "")}


def unsupported_figures(statement: str, passage: str) -> list[str]:
    """Numbers in the statement that the passage does not contain."""
    return sorted(_numbers(statement) - _numbers(passage))


@dataclass(frozen=True)
class SourcePassage:
    """One passage shown to the model: its label in the prompt, where it is, its text, and what it
    is in the database (the chunk id; anything in an eval)."""

    label: str
    locator: str
    text: str
    key: str = ""


@dataclass
class CheckedCard:
    kind: str
    statement: str
    quote: str
    passage: SourcePassage
    client: str | None
    industry: str | None
    offering: str | None  # the offering name as listed, when the model named one we have
    confidence: str


@dataclass
class SectionResult:
    summary: str
    cards: list[CheckedCard]
    dropped: list[str] = field(default_factory=list)  # why each refused card was refused
    model: str | None = None


def check_card(
    card: CardOut, passages: dict[str, SourcePassage], offerings: list[str]
) -> CheckedCard | str:
    """The card as it may be kept, or why it may not."""
    kind = card.kind.strip().lower()
    statement = " ".join(card.statement.split())
    if kind not in CARD_KINDS:
        return f"unknown kind {card.kind!r}"
    if not statement:
        return "no statement"
    passage = passages.get(card.passage.strip().strip("[]").upper())
    if passage is None:
        return f"names no passage that was shown ({card.passage!r})"
    if not quote_is_in(card.quote, passage.text):
        return f"its quote is not in {passage.label}"
    figures = unsupported_figures(statement, passage.text)
    if figures:
        return f"figures not in {passage.label}: {', '.join(figures)}"
    client = " ".join(card.client.split()) or None
    if client and _plain(client) not in _plain(passage.text):
        client = None
    if kind == CARD_CLIENT and client is None:
        return "a client card without a client named in the passage"
    named = card.offering.strip()
    offering = (
        next((name for name in offerings if names_match(named, name)), None) if named else None
    )
    confidence = card.confidence.strip().lower()
    return CheckedCard(
        kind=kind,
        statement=statement[:600],
        quote=" ".join(card.quote.split()),
        passage=passage,
        client=client[:255] if client else None,
        industry=(" ".join(card.industry.split())[:120] or None),
        offering=offering,
        confidence=confidence if confidence in CONFIDENCE_LEVELS else "medium",
    )


async def read_section(
    llm: StructuredLLM,
    document_name: str,
    offerings: list[str],
    tied: bool,
    passages: list[SourcePassage],
    max_cards: int,
) -> SectionResult:
    """Summary and checked cards for one section. Raises `LLMError` when no model answered."""
    answer = await llm.generate(
        build_section_prompt(
            document_name,
            offerings,
            tied,
            [(p.label, p.locator, p.text) for p in passages],
            max_cards,
        ),
        SectionOut,
    )
    by_label = {p.label.upper(): p for p in passages}
    kept: list[CheckedCard] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for card in answer.cards:
        checked = check_card(card, by_label, offerings)
        if isinstance(checked, str):
            dropped.append(checked)
            continue
        key = _plain(checked.statement)
        if key in seen:
            continue
        seen.add(key)
        kept.append(checked)
        if len(kept) >= max_cards:
            break
    return SectionResult(
        summary=" ".join(answer.summary.split()),
        cards=kept,
        dropped=dropped,
        model=_model_of(llm),
    )


@dataclass
class OfferingUpdate:
    description: str
    reason: str
    used: list[str]  # fact labels
    flags: list[str]  # figures or claims the facts do not back up
    model: str | None


async def draft_offering_update(
    llm: StructuredLLM,
    name: str,
    description: str | None,
    facts: list[tuple[str, str, str]],
) -> OfferingUpdate | None:
    """A better description for an offering from facts (label, statement, quote), or None when
    the model sees nothing important missing. Raises `LLMError` when no model answered."""
    answer: OfferingUpdateOut = await llm.generate(
        build_offering_update_prompt(name, description, facts), OfferingUpdateOut
    )
    proposed = " ".join(answer.description.split())[:_MAX_DESCRIPTION_CHARS]
    if not answer.change_needed or not proposed:
        return None
    if _plain(proposed) == _plain(description or ""):
        return None
    labels = {label for label, _, _ in facts}
    used = [s.strip().strip("[]").upper() for s in answer.sources]
    used = [label for label in used if label in labels]
    backing = [description or ""] + [part for _, s, q in facts for part in (s, q)]
    return OfferingUpdate(
        description=proposed,
        reason=" ".join(answer.reason.split())[:300],
        used=used,
        flags=find_unsupported_claims(proposed, backing),
        model=_model_of(llm),
    )


# -- sections of a version ------------------------------------------------------------------------


@dataclass
class Section:
    position: int
    chunks: list[DocumentChunk]

    @property
    def locator(self) -> str:
        first, last = self.chunks[0].locator, self.chunks[-1].locator
        return (first if first == last else f"{first} to {last}")[:80]


def sections_of(chunks: list[DocumentChunk], max_chars: int) -> list[Section]:
    """Passages in reading order, grouped into sections of about `max_chars` (never splitting a
    passage)."""
    sections: list[Section] = []
    current: list[DocumentChunk] = []
    size = 0
    for chunk in chunks:
        if current and size + len(chunk.text) > max_chars:
            sections.append(Section(len(sections) + 1, current))
            current, size = [], 0
        current.append(chunk)
        size += len(chunk.text)
    if current:
        sections.append(Section(len(sections) + 1, current))
    return sections


async def _offerings_for(session: AsyncSession, document: Document) -> tuple[list[Product], bool]:
    """The offerings the cards may name: the ones the document is tied to, or (for a general
    document) the live catalogue. The flag says which."""
    tied = list(
        (
            await session.execute(
                select(Product)
                .join(DocumentOffering, DocumentOffering.product_id == Product.id)
                .where(DocumentOffering.document_id == document.id)
                .order_by(Product.name)
            )
        )
        .scalars()
        .all()
    )
    if tied:
        return tied, True
    catalogue = (
        (
            await session.execute(
                select(Product)
                .where(
                    Product.organization_id == document.organization_id,
                    Product.status == STATUS_ACTIVE,
                )
                .order_by(Product.name)
                .limit(_MAX_CATALOGUE)
            )
        )
        .scalars()
        .all()
    )
    return list(catalogue), False


async def _job_cost(session: AsyncSession, job_id: uuid.UUID) -> float | None:
    try:
        total = await session.scalar(
            select(func.sum(ApiUsage.est_cost_usd)).where(ApiUsage.job_id == job_id)
        )
    except Exception:  # noqa: BLE001 - the cost is a note on the summary, never a reason to fail
        logger.warning("could not total the cost of summarising", exc_info=True)
        return None
    return round(float(total), 6) if total is not None else None


# -- the job --------------------------------------------------------------------------------------


async def process_summarise_document_job(
    session: AsyncSession, job: Job, progress: ProgressCallback
) -> dict[str, Any]:
    settings = get_settings()
    version_id = uuid.UUID(str((job.payload or {})["version_id"]))
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        return {"skipped": "the document was deleted"}
    if not cards_available(settings):
        return {"skipped": "summaries and cards are switched off or have no Gemini key"}
    if version.status != STATUS_READY:
        return {"skipped": "the document has not been read yet"}
    document = await session.get_one(Document, version.document_id)
    chunks = list(
        (
            await session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.version_id == version_id)
                .order_by(DocumentChunk.ordinal)
            )
        )
        .scalars()
        .all()
    )
    if not chunks:
        return {"skipped": "the document has no passages"}

    products, tied = await _offerings_for(session, document)
    names = [p.name for p in products]
    all_sections = sections_of(chunks, settings.documents_cards_section_chars)
    sections = all_sections[: max(1, settings.documents_cards_max_sections)]
    llm = make_card_llm(settings)
    steps = len(sections) + 2
    await progress(0, steps, stage="summarise", detail=f"Reading {len(sections)} sections")

    results: list[tuple[Section, SectionResult]] = []
    errors: list[str] = []
    for section in sections:
        passages = [
            SourcePassage(f"P{n}", chunk.locator, chunk.text, str(chunk.id))
            for n, chunk in enumerate(section.chunks, start=1)
        ]
        try:
            result = await read_section(
                llm, document.name, names, tied, passages, settings.documents_cards_max_per_section
            )
        except LLMError as exc:
            errors.append(str(exc))
            logger.info("could not summarise section %s: %s", section.position, exc)
            if "quota" in str(exc).lower():
                break  # every other section would fail the same way
            continue
        results.append((section, result))
        await progress(
            len(results), steps, stage="summarise", detail=f"Read section {section.position}"
        )

    if not results:
        await record_event(
            session,
            version,
            "summarise",
            f"Could not summarise this document ({errors[0] if errors else 'no answer'}). "
            "It will be tried again later.",
            EVENT_WARNING,
        )
        await session.commit()
        raise LLMError(errors[0] if errors else "no section could be summarised")

    overall, overall_model = await _document_summary(llm, document.name, results)
    await progress(len(sections) + 1, steps, stage="save", detail="Saving")
    # The model calls take a while: the document may have been deleted, or read again (which
    # replaces its passages), in the meantime. Then there is nothing to attach the cards to.
    used = {chunk.id for section, _ in results for chunk in section.chunks}
    if not await _passages_still_there(session, version_id, used):
        return {"skipped": _GONE}

    hidden_before = set(
        (
            await session.execute(
                select(KnowledgeCard.statement).where(
                    KnowledgeCard.version_id == version_id, KnowledgeCard.hidden
                )
            )
        )
        .scalars()
        .all()
    )
    await session.execute(delete(KnowledgeCard).where(KnowledgeCard.version_id == version_id))
    await session.execute(delete(DocumentSummary).where(DocumentSummary.version_id == version_id))
    now = datetime.now(UTC)
    session.add(
        DocumentSummary(
            organization_id=version.organization_id,
            document_id=document.id,
            version_id=version_id,
            scope=SUMMARY_DOCUMENT,
            position=0,
            locator="Whole document",
            text=overall,
            model_used=overall_model,
            prompt_version=CARDS_PROMPT_VERSION,
            created_at=now,
        )
    )
    if len(results) > 1:
        session.add_all(
            DocumentSummary(
                organization_id=version.organization_id,
                document_id=document.id,
                version_id=version_id,
                scope=SUMMARY_SECTION,
                position=section.position,
                locator=section.locator,
                text=result.summary,
                model_used=result.model,
                prompt_version=CARDS_PROMPT_VERSION,
                created_at=now,
            )
            for section, result in results
            if result.summary
        )

    by_name = {p.name: p.id for p in products}
    cards: list[KnowledgeCard] = []
    dropped = 0
    seen: set[str] = set()
    for _, result in results:
        dropped += len(result.dropped)
        for checked in result.cards:
            key = _plain(checked.statement)
            if key in seen or len(cards) >= settings.documents_cards_max_per_document:
                continue
            seen.add(key)
            product_id = by_name.get(checked.offering) if checked.offering else None
            if product_id is None and tied and len(products) == 1:
                product_id = products[0].id  # a document about one offering is about it
            cards.append(
                KnowledgeCard(
                    organization_id=version.organization_id,
                    document_id=document.id,
                    version_id=version_id,
                    chunk_id=uuid.UUID(checked.passage.key),
                    position=len(cards) + 1,
                    kind=checked.kind,
                    statement=checked.statement,
                    quote=checked.quote,
                    client=checked.client,
                    industry=checked.industry,
                    product_id=product_id,
                    confidence=checked.confidence,
                    hidden=checked.statement in hidden_before,
                    model_used=result.model,
                    prompt_version=CARDS_PROMPT_VERSION,
                    created_at=now,
                )
            )
    session.add_all(cards)
    try:
        await session.flush()
    except IntegrityError:
        # Deleted or read again between the check above and this save.
        await session.rollback()
        if not await _passages_still_there(session, version_id, used):
            return {"skipped": _GONE}
        raise

    message = (
        f"Summarised {len(results)} section{'' if len(results) == 1 else 's'} and kept "
        f"{len(cards)} knowledge card{'' if len(cards) == 1 else 's'}"
    )
    if dropped:
        message += f"; {dropped} proposed card{'' if dropped == 1 else 's'} failed the checks"
    await record_event(session, version, "summarise", message, EVENT_OK)
    if len(all_sections) > len(sections):
        await record_event(
            session,
            version,
            "summarise",
            f"Only the first {len(sections)} of {len(all_sections)} sections were summarised (the "
            "limit per document); the rest is still searchable as passages.",
            EVENT_WARNING,
        )
    if errors:
        await record_event(
            session,
            version,
            "summarise",
            f"{len(errors)} section{'' if len(errors) == 1 else 's'} could not be summarised "
            f"({errors[0]})",
            EVENT_WARNING,
        )
    await queue_embedding(session, version.organization_id, version_id)
    await session.commit()

    proposals = 0
    if settings.documents_offering_proposals_enabled and cards:
        try:
            proposals = await propose_offering_updates(session, llm, document, cards, products)
            if proposals:
                await record_event(
                    session,
                    version,
                    "summarise",
                    f"Suggested a better description for {proposals} offering"
                    f"{'' if proposals == 1 else 's'}; it waits for review under Offerings.",
                    EVENT_OK,
                )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - suggestions are extra; the cards are kept
            await session.rollback()
            logger.warning("could not suggest offering descriptions", exc_info=True)
            version = await session.get_one(DocumentVersion, version_id)
            await record_event(
                session,
                version,
                "summarise",
                f"Could not suggest offering descriptions ({exc})"[:500],
                EVENT_WARNING,
            )
            await session.commit()

    summary_row = (
        await session.execute(
            select(DocumentSummary).where(
                DocumentSummary.version_id == version_id,
                DocumentSummary.scope == SUMMARY_DOCUMENT,
            )
        )
    ).scalar_one()
    summary_row.est_cost_usd = await _job_cost(session, job.id)
    await session.commit()
    await progress(steps, steps, stage="done", detail="Done")
    return {
        "version_id": str(version_id),
        "sections": len(results),
        "cards": len(cards),
        "dropped": dropped,
        "offering_proposals": proposals,
    }


_GONE = "the document was deleted or read again while it was being summarised"


async def _passages_still_there(
    session: AsyncSession, version_id: uuid.UUID, chunk_ids: set[uuid.UUID]
) -> bool:
    """Whether every passage the cards would point at is still in the database (a fresh query, not
    the session's memory, so a delete committed elsewhere is seen)."""
    found = await session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.version_id == version_id, DocumentChunk.id.in_(list(chunk_ids)))
    )
    return found == len(chunk_ids)


async def _document_summary(
    llm: StructuredLLM, document_name: str, results: list[tuple[Section, SectionResult]]
) -> tuple[str, str | None]:
    """The whole-document summary: the section's own when there is one section, else a summary of
    the section summaries (falling back to the first section's if that call fails)."""
    written = [(section, result) for section, result in results if result.summary]
    if not written:
        return "No summary could be written for this document.", None
    if len(written) == 1:
        return written[0][1].summary, written[0][1].model
    try:
        answer = await llm.generate(
            build_document_summary_prompt(
                document_name, [(s.locator, r.summary) for s, r in written]
            ),
            DocumentSummaryOut,
        )
    except LLMError as exc:
        logger.info("could not write the document summary: %s", exc)
        return written[0][1].summary, written[0][1].model
    text = " ".join(answer.summary.split())
    return (text, _model_of(llm)) if text else (written[0][1].summary, written[0][1].model)


# -- better offering descriptions, as proposals ---------------------------------------------------


def _facts_hash(cards: list[KnowledgeCard]) -> str:
    raw = "|".join(sorted(_plain(c.statement) for c in cards))
    return hashlib.sha256(raw.encode()).hexdigest()


async def propose_offering_updates(
    session: AsyncSession,
    llm: StructuredLLM,
    document: Document,
    cards: list[KnowledgeCard],
    products: list[Product],
) -> int:
    """For each live offering the cards are about, asks whether its description misses something
    the cards show, and writes a proposal when it does. A waiting proposal from this document for
    the same offering is replaced; one a person rejected for the same facts is not asked again.
    Returns how many proposals were written."""
    usable = [c for c in cards if not c.hidden and c.confidence != "low" and c.product_id]
    by_product: dict[uuid.UUID, list[KnowledgeCard]] = {}
    for card in usable:
        assert card.product_id is not None
        by_product.setdefault(card.product_id, []).append(card)
    live = {p.id: p for p in products if p.status == STATUS_ACTIVE}
    written = 0
    for product_id, facts_cards in by_product.items():
        product = live.get(product_id)
        if product is None:
            continue
        facts_cards = facts_cards[:_MAX_FACTS_PER_OFFERING]
        digest = _facts_hash(facts_cards)
        earlier = (
            (
                await session.execute(
                    select(OfferingProposal).where(
                        OfferingProposal.organization_id == document.organization_id,
                        OfferingProposal.origin == LANE_DOCUMENT,
                        OfferingProposal.product_id == product_id,
                        OfferingProposal.document_id == document.id,
                        OfferingProposal.status.in_([PROPOSAL_PENDING, PROPOSAL_REJECTED]),
                    )
                )
            )
            .scalars()
            .all()
        )
        if any(p.status == PROPOSAL_REJECTED and p.content_hash == digest for p in earlier):
            continue
        if any(p.status == PROPOSAL_PENDING and p.content_hash == digest for p in earlier):
            continue  # already waiting for these very facts
        facts = [(f"F{n}", c.statement, c.quote) for n, c in enumerate(facts_cards, start=1)]
        update = await draft_offering_update(llm, product.name, product.description, facts)
        for old in earlier:
            if old.status == PROPOSAL_PENDING:
                await session.delete(old)
        if update is None:
            continue
        used = set(update.used) or {label for label, _, _ in facts}
        excerpt = "\n".join(statement for label, statement, _ in facts if label in used)
        session.add(
            OfferingProposal(
                organization_id=document.organization_id,
                product_id=product_id,
                change=CHANGE_CHANGED,
                status=PROPOSAL_PENDING,
                kind=product.kind,
                name=product.name,
                description=update.description,
                source_url=f"document:{document.id}",
                content_hash=digest,
                origin=LANE_DOCUMENT,
                source_excerpt=(f"{update.reason}\n{excerpt}" if update.reason else excerpt),
                grounding_flags=update.flags or None,
                model_used=update.model,
                prompt_version=CARDS_PROMPT_VERSION,
                document_id=document.id,
            )
        )
        written += 1
    await session.flush()
    return written


# -- catching up ----------------------------------------------------------------------------------


def _summarised(version_column: Any) -> Any:
    return (
        select(DocumentSummary.id)
        .where(
            DocumentSummary.version_id == version_column,
            DocumentSummary.scope == SUMMARY_DOCUMENT,
            DocumentSummary.prompt_version == CARDS_PROMPT_VERSION,
        )
        .exists()
    )


async def queue_summary(
    session: AsyncSession, organization_id: uuid.UUID, version_id: uuid.UUID
) -> None:
    """Queue the summary and cards for a version that has just been read (nothing while off)."""
    if cards_available(get_settings()):
        await enqueue_job(
            session, organization_id, JOB_TYPE_SUMMARISE_DOCUMENT, {"version_id": str(version_id)}
        )


async def summarise_again(
    session: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> Job:
    """A person asked for a new summary and cards (for example after a quota ran out, or when the
    cards look wrong). Cards a person hid stay hidden when they come back with the same words."""
    document = await _document(session, organization_id, document_id)
    if not cards_available(get_settings()):
        raise CannotReprocessError("Summaries are switched off, or no Gemini key is set.")
    version = (
        await session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id, DocumentVersion.is_current
            )
        )
    ).scalar_one_or_none()
    if version is None or version.status != STATUS_READY or not version.chunk_count:
        raise CannotReprocessError("This document has not been read yet.")
    busy = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.job_type == JOB_TYPE_SUMMARISE_DOCUMENT,
            Job.payload["version_id"].as_string() == str(version.id),
            Job.status.in_([STATUS_PENDING, STATUS_RUNNING]),
        )
    )
    if busy:
        raise CannotReprocessError("A summary is already being written for this document.")
    await record_audit(session, organization_id, document, AUDIT_SUMMARISE)
    await record_event(session, version, "summarise", "Queued to be summarised again")
    job = await enqueue_job(
        session, organization_id, JOB_TYPE_SUMMARISE_DOCUMENT, {"version_id": str(version.id)}
    )
    await session.flush()
    return job


async def queue_missing_summaries(session: AsyncSession) -> int:
    """Queues the job for each current version with no summary from the current prompt, unless one
    is waiting or running, or a recent attempt failed. Called by the worker every hour."""
    if not cards_available(get_settings()):
        return 0
    versions = (
        await session.execute(
            select(DocumentVersion.id, DocumentVersion.organization_id).where(
                DocumentVersion.is_current,
                DocumentVersion.status == STATUS_READY,
                DocumentVersion.chunk_count > 0,
                ~_summarised(DocumentVersion.id),
            )
        )
    ).all()
    cutoff = datetime.now(UTC) - _RETRY_AFTER
    queued = 0
    for version_id, organization_id in versions:
        busy = await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.job_type == JOB_TYPE_SUMMARISE_DOCUMENT,
                Job.payload["version_id"].as_string() == str(version_id),
                or_(
                    Job.status.in_([STATUS_PENDING, STATUS_RUNNING]),
                    and_(Job.status != STATUS_DONE, Job.created_at > cutoff),
                ),
            )
        )
        if busy:
            continue
        await queue_summary(session, organization_id, version_id)
        queued += 1
    return queued
