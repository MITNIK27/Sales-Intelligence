"""Finding the passages that answer a question: by meaning and by words, merged.

Two lists are built. One is the passages whose vectors are nearest the question's vector (finds
"cut the cost of building software" in a passage that says "reduce development spend"). The other is
passages that share words with the question, ranked by how many and how close together (finds exact
names, product codes and numbers that a vector blurs). They are merged by reciprocal rank fusion,
which uses only each passage's place in each list, so the two different kinds of score never have
to be compared. A passage in both lists rises to the top.

Only the current version of each document is searched. When the question is about particular
offerings, passages of documents tied to them come first (a small boost) and general documents still
count; documents tied only to other offerings are left out.

When meaning search is off, has no key, or fails, the answer is still given from words alone and
says so, so a quota problem never means "no results"."""

import re
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Text, cast, func, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.documents.embedding import embeddings_available, make_embedder, needs_vector
from app.modules.documents.models import (
    STATUS_READY,
    Document,
    DocumentChunk,
    DocumentOffering,
    DocumentVersion,
)
from app.modules.documents.vector_store import PgVectorStore, VectorStore
from app.modules.products.models import Product

_RRF_K = 60  # the usual constant: how fast a lower place stops mattering
_OFFERING_BOOST = 1.25
MAX_QUESTION_CHARS = 500

Mode = Literal["meaning_and_words", "words_only"]


class EmptyQuestionError(ValueError):
    pass


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    version: int
    locator: str
    heading_path: str | None
    text: str
    offerings: list[tuple[uuid.UUID, str]]
    score: float
    similarity: float | None  # cosine to the question, when the passage was found by meaning
    word_match: bool
    about_offering: bool  # the document is tied to an offering the question named


@dataclass
class SearchOutcome:
    hits: list[Hit]
    mode: Mode
    note: str | None = None
    indexed: int = 0
    total: int = 0


def _clean(question: str) -> str:
    cleaned = " ".join(question.split())[:MAX_QUESTION_CHARS]
    if not re.search(r"\w", cleaned):
        raise EmptyQuestionError("Type a question or some words to search for.")
    return cleaned


def _any_word_query(question: str):  # type: ignore[no-untyped-def]
    """A tsquery that matches a passage having ANY of the question's words (stop words and endings
    are handled by the 'english' configuration), so a whole sentence still finds something."""
    plain = func.plainto_tsquery("english", question)
    return cast(func.replace(cast(plain, Text), " & ", " | "), TSQUERY)


async def _document_scope(
    session: AsyncSession, organization_id: uuid.UUID, product_ids: list[uuid.UUID]
) -> tuple[set[uuid.UUID] | None, set[uuid.UUID]]:
    """(documents that may be searched, documents tied to a named offering). No named offering
    means everything may be searched and nothing is boosted."""
    if not product_ids:
        return None, set()
    tied = set(
        (
            await session.execute(
                select(DocumentOffering.document_id).where(
                    DocumentOffering.product_id.in_(product_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    with_any = select(DocumentOffering.document_id)
    general = set(
        (
            await session.execute(
                select(Document.id).where(
                    Document.organization_id == organization_id, Document.id.not_in(with_any)
                )
            )
        )
        .scalars()
        .all()
    )
    return tied | general, tied


async def search(
    session: AsyncSession,
    organization_id: uuid.UUID,
    question: str,
    *,
    product_ids: list[uuid.UUID] | None = None,
    limit: int = 8,
    store: VectorStore | None = None,
) -> SearchOutcome:
    settings = get_settings()
    question = _clean(question)
    limit = max(1, min(limit, settings.documents_search_max_results))
    candidates = settings.documents_search_candidates
    allowed, tied = await _document_scope(session, organization_id, product_ids or [])
    if allowed is not None and not allowed:
        return SearchOutcome([], "words_only", "No document is about those offerings yet.")

    # passages and how many have a vector, for honesty about what meaning search can see
    base = (
        select(func.count())
        .select_from(DocumentChunk)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
        .where(
            DocumentChunk.organization_id == organization_id,
            DocumentVersion.is_current,
            DocumentVersion.status == STATUS_READY,
        )
    )
    total = await session.scalar(base) or 0
    missing = (
        await session.scalar(base.where(needs_vector(settings.documents_embedding_model))) or 0
    )

    # --- by words
    tsq = _any_word_query(question)
    word_stmt = (
        select(DocumentChunk.id, func.ts_rank_cd(DocumentChunk.tsv, tsq).label("rank"))
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
        .where(
            DocumentChunk.organization_id == organization_id,
            DocumentVersion.is_current,
            DocumentChunk.tsv.op("@@")(tsq),
        )
        .order_by(func.ts_rank_cd(DocumentChunk.tsv, tsq).desc(), DocumentChunk.id)
        .limit(candidates)
    )
    if allowed is not None:
        word_stmt = word_stmt.where(DocumentChunk.document_id.in_(list(allowed)))
    word_ids = [row[0] for row in (await session.execute(word_stmt)).all()]

    # --- by meaning
    mode: Mode = "words_only"
    note: str | None = None
    similar: dict[uuid.UUID, float] = {}
    if not embeddings_available(settings):
        note = "Searching by words only: meaning search is switched off."
    else:
        try:
            embedded = await make_embedder(settings).embed([question], "query")
            hits = await (store or PgVectorStore()).search(
                session,
                organization_id=organization_id,
                vector=embedded.vectors[0],
                model=embedded.model,
                limit=candidates,
                document_ids=allowed,
            )
            similar = {
                h.chunk_id: h.similarity
                for h in hits
                if h.similarity >= settings.documents_min_similarity
            }
            mode = "meaning_and_words"
            if missing and total:
                note = (
                    f"{total - missing} of {total} passages are indexed for meaning search so far."
                )
        except GeminiClientError as exc:
            note = f"Searching by words only: meaning search is unavailable right now ({exc})"

    # --- merge
    ranked_by_meaning = list(similar)  # already nearest first
    fused: dict[uuid.UUID, float] = {}
    for ranking in (ranked_by_meaning, word_ids):
        for place, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + place)
    if not fused:
        return SearchOutcome([], mode, note, total - missing, total)

    rows = (
        await session.execute(
            select(DocumentChunk, Document.name, DocumentVersion.version)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
            .where(DocumentChunk.id.in_(list(fused)))
        )
    ).all()
    document_ids = {chunk.document_id for chunk, _, _ in rows}
    offerings: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {d: [] for d in document_ids}
    for document_id, product_id, name in (
        await session.execute(
            select(DocumentOffering.document_id, Product.id, Product.name)
            .join(Product, Product.id == DocumentOffering.product_id)
            .where(DocumentOffering.document_id.in_(document_ids))
            .order_by(Product.name)
        )
    ).all():
        offerings[document_id].append((product_id, name))

    word_set = set(word_ids)
    out: list[Hit] = []
    for chunk, document_name, version in rows:
        about = chunk.document_id in tied
        out.append(
            Hit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=document_name,
                version=version,
                locator=chunk.locator,
                heading_path=chunk.heading_path,
                text=chunk.text,
                offerings=offerings.get(chunk.document_id, []),
                score=fused[chunk.id] * (_OFFERING_BOOST if about else 1.0),
                similarity=similar.get(chunk.id),
                word_match=chunk.id in word_set,
                about_offering=about,
            )
        )
    out.sort(key=lambda h: (-h.score, str(h.chunk_id)))
    return SearchOutcome(out[:limit], mode, note, total - missing, total)
