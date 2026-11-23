"""What our own documents say, packed for a prompt (Phase 8d).

The prompts that reason about our offerings (offering fit, the recommendation, area suggestions and
the Quick Look summary) are given a few passages from the library, each labelled [K1], [K2], ..., so
the model can describe what an offering really does and has delivered, and say which passage it
used. The passages are our own material, but they came from uploaded files, so they are fenced as
untrusted text like anything else read from outside.

These passages are about US, never evidence about the prospect: a fit, an area or a "yes" still
needs evidence from the company's own research.

A prompt that carries passages goes to Gemini only (docs/ai-governance.md, G1). When no such vendor
can answer, the same question is asked without the passages, so the flow never stops for them.

Nothing here may break the flow that asked: with documents off, an empty library or a failed search,
the answer is simply "no knowledge" and the prompt is the one it always was."""

import hashlib
import logging
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.documents import retrieval
from app.modules.documents.models import (
    STATUS_READY,
    Document,
    DocumentChunk,
    DocumentOffering,
    DocumentVersion,
)
from app.modules.llm.structured import FallbackStructuredLLM, LLMError, StructuredLLM
from app.modules.llm.untrusted import wrap_untrusted

logger = logging.getLogger(__name__)

_PER_PASSAGE_CHARS = 900
_LABEL = re.compile(r"\[?\bK(\d+)\b\]?")
# The vendors a prompt with passages from our documents may go to (G1).
KNOWLEDGE_VENDORS = {"gemini"}


@dataclass(frozen=True)
class Passage:
    """One passage to show a model, from the library or (in evals) written into a case."""

    document_name: str
    locator: str
    text: str
    chunk_id: str = ""
    document_id: str = ""
    version: int = 0


@dataclass
class Knowledge:
    block: str = ""  # fenced passages ready for a prompt; empty when there is nothing to add
    refs: list[dict[str, Any]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.refs)

    def cited_in(self, *texts: str | None) -> list[dict[str, Any]]:
        """The refs with `cited` set for every label that appears in the given texts."""
        used = {f"K{n}" for text in texts for n in _LABEL.findall(text or "")}
        return [{**ref, "cited": ref["label"] in used} for ref in self.refs]


def pack(passages: Iterable[Passage], max_chars: int) -> Knowledge:
    """Label, trim and fence passages for a prompt, best first, within `max_chars`."""
    parts: list[str] = []
    refs: list[dict[str, Any]] = []
    budget = max_chars
    for passage in passages:
        text = " ".join(passage.text.split())
        if not text:
            continue
        if len(text) > _PER_PASSAGE_CHARS:
            text = text[:_PER_PASSAGE_CHARS].rsplit(" ", 1)[0] + " ..."
        label = f"K{len(refs) + 1}"
        entry = f"[{label}] ({passage.document_name}, {passage.locator})\n{text}"
        if len(entry) > budget:
            break
        budget -= len(entry)
        parts.append(entry)
        refs.append(
            {
                "label": label,
                "chunk_id": passage.chunk_id,
                "document_id": passage.document_id,
                "document_name": passage.document_name,
                "version": passage.version,
                "locator": passage.locator,
            }
        )
    if not refs:
        return Knowledge()
    return Knowledge(block=wrap_untrusted("\n\n".join(parts), "our documents"), refs=refs)


def _relevant_documents(organization_id: uuid.UUID, product_ids: list[uuid.UUID]) -> Any:
    """Documents about any of these offerings, plus general ones (tied to no offering). With no
    offerings named, every document."""
    if not product_ids:
        return select(Document.id).where(Document.organization_id == organization_id)
    tied = select(DocumentOffering.document_id).where(DocumentOffering.product_id.in_(product_ids))
    with_any = select(DocumentOffering.document_id)
    return select(Document.id).where(
        Document.organization_id == organization_id,
        Document.id.in_(tied) | Document.id.not_in(with_any),
    )


async def library_hash(
    session: AsyncSession, organization_id: uuid.UUID, product_ids: list[uuid.UUID]
) -> str | None:
    """A fingerprint of the documents that could be shown for these offerings (all documents when
    none are named): which versions are current and how many of their passages are indexed. None
    when documents are off or there are none, so results made before documents existed stay
    valid."""
    settings = get_settings()
    if not settings.documents_enabled or settings.documents_knowledge_passages <= 0:
        return None
    rows = (
        await session.execute(
            select(
                DocumentVersion.document_id,
                DocumentVersion.id,
                func.count(DocumentChunk.embedding),
            )
            .outerjoin(DocumentChunk, DocumentChunk.version_id == DocumentVersion.id)
            .where(
                DocumentVersion.is_current,
                DocumentVersion.status == STATUS_READY,
                DocumentVersion.document_id.in_(_relevant_documents(organization_id, product_ids)),
            )
            .group_by(DocumentVersion.document_id, DocumentVersion.id)
            .order_by(DocumentVersion.document_id)
        )
    ).all()
    if not rows:
        return None
    text = "|".join(f"{d}:{v}:{n}" for d, v, n in rows)
    return hashlib.sha256(text.encode()).hexdigest()


async def gather(
    session: AsyncSession,
    organization_id: uuid.UUID,
    question: str,
    product_ids: list[uuid.UUID],
) -> Knowledge:
    """The passages that best answer `question` among documents about these offerings (and general
    ones; all documents when none are named), fenced and labelled for a prompt."""
    settings = get_settings()
    if not settings.documents_enabled or settings.documents_knowledge_passages <= 0:
        return Knowledge()
    try:
        outcome = await retrieval.search(
            session,
            organization_id,
            question,
            product_ids=product_ids,
            limit=settings.documents_knowledge_passages,
        )
    except Exception:  # noqa: BLE001 - knowledge is extra; the flow that asked must go on
        logger.warning("could not search the documents for a prompt", exc_info=True)
        return Knowledge()
    return pack(
        (
            Passage(
                document_name=hit.document_name,
                locator=hit.locator,
                text=hit.text,
                chunk_id=str(hit.chunk_id),
                document_id=str(hit.document_id),
                version=hit.version,
            )
            for hit in outcome.hits
        ),
        settings.documents_knowledge_max_chars,
    )


async def generate_with_knowledge[T: BaseModel](
    llm: StructuredLLM,
    prompt: str,
    plain_prompt: str,
    schema: type[T],
    knowledge: Knowledge,
) -> tuple[T, bool]:
    """The model's answer, and whether it saw the passages. `prompt` carries them, `plain_prompt` is
    the same question without them. With passages the call goes to Gemini only (G1); if no such
    vendor is in the chain, or none can answer, the plain question goes to the whole chain."""
    if not knowledge:
        return await llm.generate(plain_prompt, schema), False
    chain = llm.restricted_to(KNOWLEDGE_VENDORS) if isinstance(llm, FallbackStructuredLLM) else llm
    if isinstance(chain, FallbackStructuredLLM) and chain.is_empty:
        return await llm.generate(plain_prompt, schema), False
    try:
        return await chain.generate(prompt, schema), True
    except LLMError as exc:
        logger.info("could not answer with our documents (%s); asking without them", exc)
        return await llm.generate(plain_prompt, schema), False
