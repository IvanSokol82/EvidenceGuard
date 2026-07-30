import hashlib
from typing import Protocol

from src.config import settings


class EmbeddingsProvider(Protocol):
    async def embed_query(self, text: str) -> list[float]:
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...


class MockEmbeddingsProvider:
    """
    Deterministic mock embedding provider.
    Generates a normalized 1536-dimensional vector derived deterministically from the SHA256 of text input.
    Guarantees reproducible, isolated, network-free tests.
    """

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    async def embed_query(self, text: str) -> list[float]:
        return self._generate_vector(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]

    def _generate_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Seed pseudo-vector floats between -1.0 and 1.0
        vec = []
        for i in range(self.dimension):
            byte_val = digest[i % len(digest)]
            val = (byte_val / 255.0) * 2.0 - 1.0
            vec.append(round(val, 6))
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [round(v / norm, 6) for v in vec]
        return vec


def get_embeddings_provider() -> EmbeddingsProvider:
    # Always return mock for local dev / tests unless configured otherwise
    return MockEmbeddingsProvider(dimension=settings.EMBEDDING_DIMENSION)
