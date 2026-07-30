import asyncio
import uuid

from src.database.session import SqliteAsyncSessionLocal
from src.rag.embeddings import get_embeddings_provider
from src.rag.retrieval import HybridRetriever

DEFAULT_ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


async def debug_rag():
    print("[Debug RAG] Testing retrieval on SQLite...")
    embeddings = get_embeddings_provider()
    query_text = "Do you encrypt customer data at rest and in transit?"
    query_vector = await embeddings.embed_query(query_text)

    async with SqliteAsyncSessionLocal() as db:
        retriever = HybridRetriever(db=db)
        items = await retriever.retrieve(
            query_text=query_text,
            query_vector=query_vector,
            top_n=5,
            target_organization_id=DEFAULT_ORG_ID,
        )
        print(f"[Result] Retrieved items count: {len(items)}")
        for item in items:
            print(f"  - [{item.document_title}] (Confidence: {item.confidence_score}): {item.content[:80]}")


if __name__ == "__main__":
    asyncio.run(debug_rag())
