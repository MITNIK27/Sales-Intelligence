"""Where passage vectors are searched. `VectorStore` is the seam: today the vectors live in the same
Postgres as everything else (pgvector), and a dedicated vector database could replace it later
without changing retrieval."""

import uuid
from collections.abc import Collection
from typing import NamedTuple, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import DocumentChunk, DocumentVersion, KnowledgeCard


class VectorHit(NamedTuple):
    chunk_id: uuid.UUID  # the passage, or the knowledge card for `search_cards`
    similarity: float  # cosine, 1 is identical


class VectorStore(Protocol):
    async def search(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        vector: list[float],
        model: str,
        limit: int,
        document_ids: Collection[uuid.UUID] | None = None,
    ) -> list[VectorHit]: ...

    async def search_cards(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        vector: list[float],
        model: str,
        limit: int,
        document_ids: Collection[uuid.UUID] | None = None,
    ) -> list[VectorHit]: ...


class PgVectorStore:
    """Nearest passages by cosine distance, over the current version of each document only and
    only passages made by `model` (vectors from two models are not comparable)."""

    async def search(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        vector: list[float],
        model: str,
        limit: int,
        document_ids: Collection[uuid.UUID] | None = None,
    ) -> list[VectorHit]:
        distance = DocumentChunk.embedding.cosine_distance(vector)
        stmt = (
            select(DocumentChunk.id, distance.label("distance"))
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
            .where(
                DocumentChunk.organization_id == organization_id,
                DocumentVersion.is_current,
                DocumentChunk.embedding.is_not(None),
                DocumentChunk.embedding_model == model,
            )
            .order_by(distance)
            .limit(limit)
        )
        if document_ids is not None:
            stmt = stmt.where(DocumentChunk.document_id.in_(list(document_ids)))
        rows = (await session.execute(stmt)).all()
        return [VectorHit(chunk_id, 1.0 - float(dist)) for chunk_id, dist in rows]

    async def search_cards(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        vector: list[float],
        model: str,
        limit: int,
        document_ids: Collection[uuid.UUID] | None = None,
    ) -> list[VectorHit]:
        """Nearest knowledge cards, from current versions only, leaving out hidden ones."""
        distance = KnowledgeCard.embedding.cosine_distance(vector)
        stmt = (
            select(KnowledgeCard.id, distance.label("distance"))
            .join(DocumentVersion, DocumentVersion.id == KnowledgeCard.version_id)
            .where(
                KnowledgeCard.organization_id == organization_id,
                DocumentVersion.is_current,
                ~KnowledgeCard.hidden,
                KnowledgeCard.embedding.is_not(None),
                KnowledgeCard.embedding_model == model,
            )
            .order_by(distance)
            .limit(limit)
        )
        if document_ids is not None:
            stmt = stmt.where(KnowledgeCard.document_id.in_(list(document_ids)))
        rows = (await session.execute(stmt)).all()
        return [VectorHit(card_id, 1.0 - float(dist)) for card_id, dist in rows]
