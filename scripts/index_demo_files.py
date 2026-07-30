import asyncio
import hashlib
import uuid

from sqlalchemy import select

from src.database.models import DocumentChunk, KnowledgeDocument
from src.database.session import (
    AsyncSessionLocal,
    Base,
    SqliteAsyncSessionLocal,
    engine,
    sqlite_engine,
)
from src.rag.embeddings import get_embeddings_provider

DEFAULT_ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


async def index_demo_policy():
    print("[Indexing] Indexing demo policy file into Knowledge Base...")

    file_path = "demo_files/Acme_Cloud_Security_Policy_2026.md"
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    session_factory = AsyncSessionLocal
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        session_factory = SqliteAsyncSessionLocal
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Check existing
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.content_hash == content_hash)
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            print("[Info] Demo document already indexed in Knowledge Base.")
            return

        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            organization_id=DEFAULT_ORG_ID,
            title="Acme Cloud Security & Compliance Policy 2026",
            document_type="policy",
            owner_team="Security",
            approval_status="approved",
            version="v2026.1",
            content_hash=content_hash,
            source_uri=file_path,
        )
        db.add(doc)
        await db.flush()

        embeddings = get_embeddings_provider()
        sections = content.split("\n\n")
        for idx, sec in enumerate(sections):
            if not sec.strip():
                continue
            vec = await embeddings.embed_query(sec.strip())
            chunk = DocumentChunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                chunk_index=idx,
                content=sec.strip(),
                embedding=vec,
                page_reference=f"Section {idx + 1}",
                section_reference=doc.title,
                approval_status_snapshot="approved",
                document_version_snapshot=doc.version,
            )
            db.add(chunk)

        await db.commit()
        print("[Success] Demo document successfully indexed into Knowledge Base!")


if __name__ == "__main__":
    asyncio.run(index_demo_policy())
