import uuid

import pytest

from src.rag.chunking import chunk_text
from src.rag.embeddings import MockEmbeddingsProvider
from src.rag.parser import parse_document
from src.rag.retrieval import RetrievedEvidence, compute_rrf_score


def test_parse_text_and_chunking():
    raw_text = "Section 1: Data Encryption\n\nAll customer data at rest is encrypted using AES-256."
    sections = parse_document(raw_text.encode("utf-8"), "policy.txt")
    assert len(sections) == 1
    assert "AES-256" in sections[0].content

    chunks = chunk_text(sections[0].content, max_chunk_size=100)
    assert len(chunks) >= 1
    assert "AES-256" in chunks[0].content


@pytest.mark.asyncio
async def test_mock_embeddings_provider_deterministic():
    provider = MockEmbeddingsProvider(dimension=1536)
    vec1 = await provider.embed_query("AES-256 encryption at rest")
    vec2 = await provider.embed_query("AES-256 encryption at rest")
    vec3 = await provider.embed_query("Unrelated marketing text")

    assert len(vec1) == 1536
    assert vec1 == vec2  # Deterministic equality
    assert vec1 != vec3  # Different text yields different vector


def test_rrf_score_calculation_and_trust_multipliers():
    # Test RRF formula: (1 / (60 + 1) + 1 / (60 + 1)) * 1.2
    high_trust_score = compute_rrf_score(vector_rank=1, keyword_rank=1, k=60, trust_multiplier=1.2)
    low_trust_score = compute_rrf_score(vector_rank=1, keyword_rank=1, k=60, trust_multiplier=0.5)
    zero_trust_score = compute_rrf_score(vector_rank=1, keyword_rank=1, k=60, trust_multiplier=0.0)

    assert high_trust_score > low_trust_score
    assert zero_trust_score == 0.0


def test_retrieved_evidence_sorting_by_rrf_score():
    ev1 = RetrievedEvidence(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Security Policy 2026",
        document_type="policy",
        owner_team="Security",
        version="v1.0",
        page_reference="Page 1",
        section_reference="Encryption",
        content="Data is encrypted using AES-256.",
        semantic_rank=1,
        keyword_rank=1,
        rrf_score=0.039,
        confidence_score=1.0,
        evidence_type="policy",
    )

    ev2 = RetrievedEvidence(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Marketing Brochure",
        document_type="marketing",
        owner_team="Marketing",
        version="v1.0",
        page_reference=None,
        section_reference=None,
        content="We offer top tier security.",
        semantic_rank=2,
        keyword_rank=5,
        rrf_score=0.015,
        confidence_score=0.45,
        evidence_type="marketing",
    )

    items = [ev2, ev1]
    items.sort(key=lambda x: x.rrf_score, reverse=True)
    assert items[0] == ev1  # Approved security policy outranks marketing text
