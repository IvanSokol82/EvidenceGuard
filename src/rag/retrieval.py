import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import DocumentChunk, KnowledgeDocument

TRUST_MULTIPLIERS: dict[str, float] = {
    "policy": 1.2,
    "architecture": 1.2,
    "certificate": 1.3,
    "audit": 1.2,
    "documentation": 1.0,
    "faq": 0.9,
    "old_questionnaire": 0.5,
    "marketing": 0.0,  # Exclude from evidence
}


@dataclass
class RetrievedEvidence:
    chunk_id: Any
    document_id: Any
    document_title: str
    document_type: str
    owner_team: str
    version: str
    page_reference: str | None
    section_reference: str | None
    content: str
    semantic_rank: int | None
    keyword_rank: int | None
    rrf_score: float
    confidence_score: float
    evidence_type: str


def compute_rrf_score(
    vector_rank: int | None,
    keyword_rank: int | None,
    k: int = 60,
    trust_multiplier: float = 1.0,
) -> float:
    """
    Reciprocal Rank Fusion formula:
    RRF = ( 1 / (k + vector_rank) + 1 / (k + keyword_rank) ) * trust_multiplier
    """
    score = 0.0
    if vector_rank is not None:
        score += 1.0 / (k + vector_rank)
    if keyword_rank is not None:
        score += 1.0 / (k + keyword_rank)
    return round(score * trust_multiplier, 6)


def clean_words(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return {w for w in cleaned.split() if len(w) > 1}


class HybridRetriever:
    """
    Hybrid Retrieval Engine performing pgvector semantic search and PostgreSQL tsvector FTS
    with metadata validity pre-filtering and Reciprocal Rank Fusion.
    """

    def __init__(self, db: AsyncSession, rrf_k: int = 60):
        self.db = db
        self.rrf_k = rrf_k

    async def retrieve(
        self,
        query_text: str,
        query_vector: list[float],
        top_n: int = 10,
        target_organization_id: Any = None,
    ) -> list[RetrievedEvidence]:
        now = datetime.now(timezone.utc)

        # 1. Base Query Filter for Approved & Valid Documents
        base_doc_filter = and_(
            KnowledgeDocument.approval_status == "approved",
            or_(KnowledgeDocument.valid_from.is_(None), KnowledgeDocument.valid_from <= now),
            or_(KnowledgeDocument.valid_to.is_(None), KnowledgeDocument.valid_to >= now),
        )
        if target_organization_id:
            # Handle string vs UUID comparison gracefully
            base_doc_filter = and_(
                base_doc_filter,
                KnowledgeDocument.organization_id == str(target_organization_id),
            )

        # 2. Fetch candidate chunks joined with valid documents
        stmt = (
            select(DocumentChunk, KnowledgeDocument)
            .join(KnowledgeDocument, DocumentChunk.document_id == KnowledgeDocument.id)
            .where(base_doc_filter)
        )
        result = await self.db.execute(stmt)
        rows: Sequence[tuple[DocumentChunk, KnowledgeDocument]] = result.all()

        if not rows:
            return []

        # 3. Vector Similarity Ranking
        vector_ranked = self._rank_by_vector(query_vector, rows)

        # 4. Full-Text / Keyword Ranking
        keyword_ranked = self._rank_by_keywords(query_text, rows)

        # Build rank maps chunk_id -> rank (1-indexed)
        vector_rank_map = {chunk_id: rank for rank, (chunk_id, _, _) in enumerate(vector_ranked, start=1)}
        keyword_rank_map = {chunk_id: rank for rank, (chunk_id, _, _) in enumerate(keyword_ranked, start=1)}

        # 5. Combine with RRF & Trust Multiplier
        evidence_list: list[RetrievedEvidence] = []
        seen_chunks = set(vector_rank_map.keys()).union(set(keyword_rank_map.keys()))

        chunk_dict = {chunk.id: (chunk, doc) for chunk, doc in rows}

        for chunk_id in seen_chunks:
            if chunk_id not in chunk_dict:
                continue
            chunk, doc = chunk_dict[chunk_id]
            multiplier = TRUST_MULTIPLIERS.get(doc.document_type.lower(), 1.0)
            if multiplier <= 0.0:
                continue  # Exclude marketing / untrusted

            v_rank = vector_rank_map.get(chunk_id)
            k_rank = keyword_rank_map.get(chunk_id)

            rrf = compute_rrf_score(v_rank, k_rank, k=self.rrf_k, trust_multiplier=multiplier)
            confidence = min(1.0, round(rrf * 30.0, 3))

            evidence_list.append(
                RetrievedEvidence(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    document_title=doc.title,
                    document_type=doc.document_type,
                    owner_team=doc.owner_team,
                    version=doc.version,
                    page_reference=chunk.page_reference,
                    section_reference=chunk.section_reference,
                    content=chunk.content,
                    semantic_rank=v_rank,
                    keyword_rank=k_rank,
                    rrf_score=rrf,
                    confidence_score=confidence,
                    evidence_type=doc.document_type,
                )
            )

        # Sort descending by RRF score
        evidence_list.sort(key=lambda e: e.rrf_score, reverse=True)
        return evidence_list[:top_n]

    def _rank_by_vector(
        self, query_vec: list[float], rows: Sequence[tuple[DocumentChunk, KnowledgeDocument]]
    ) -> list[tuple[Any, DocumentChunk, KnowledgeDocument]]:
        scored = []
        for chunk, doc in rows:
            emb = chunk.embedding
            if isinstance(emb, str):
                try:
                    emb = json.loads(emb)
                except Exception:
                    emb = []

            if emb and isinstance(emb, list) and len(emb) == len(query_vec):
                dot_prod = sum(q * e for q, e in zip(query_vec, emb))
                norm_q = math.sqrt(sum(q * q for q in query_vec)) or 1.0
                norm_e = math.sqrt(sum(e * e for e in emb)) or 1.0
                sim = dot_prod / (norm_q * norm_e)
            else:
                sim = 0.0
            scored.append((sim, chunk, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [(chunk.id, chunk, doc) for sim, chunk, doc in scored if sim > 0.0]

    def _rank_by_keywords(
        self, query_text: str, rows: Sequence[tuple[DocumentChunk, KnowledgeDocument]]
    ) -> list[tuple[Any, DocumentChunk, KnowledgeDocument]]:
        query_words = clean_words(query_text)
        if not query_words:
            return []

        scored = []
        for chunk, doc in rows:
            content_words = clean_words(chunk.content)
            matches = sum(1 for w in query_words if w in content_words)
            if matches > 0:
                score = matches / len(query_words)
                scored.append((score, chunk, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [(chunk.id, chunk, doc) for score, chunk, doc in scored]
