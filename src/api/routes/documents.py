import hashlib
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database.models import DocumentChunk, DocumentVersion, KnowledgeDocument
from src.database.session import get_db_session
from src.rag.chunking import chunk_text
from src.rag.embeddings import get_embeddings_provider
from src.rag.parser import parse_document
from src.schemas.models import KnowledgeDocumentRead

router = APIRouter(prefix="/documents", tags=["Knowledge Documents"])


@router.post("/upload", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    organization_id: uuid.UUID = Form(...),
    title: str = Form(...),
    document_type: str = Form("policy"),
    owner_team: str = Form("Security"),
    version: str = Form("v1.0"),
    sensitivity_level: str = Form("internal"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
):
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Check duplicate hash
    existing_stmt = select(KnowledgeDocument).where(KnowledgeDocument.content_hash == content_hash)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="A document with identical content already exists."
        )

    # Save physical file
    file_id = uuid.uuid4()
    file_filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(settings.STORAGE_DIR, file_filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Create KnowledgeDocument
    document = KnowledgeDocument(
        id=file_id,
        organization_id=organization_id,
        title=title,
        document_type=document_type,
        owner_team=owner_team,
        approval_status="approved",
        version=version,
        sensitivity_level=sensitivity_level,
        content_hash=content_hash,
        source_uri=file_path,
    )
    db.add(document)

    # Create DocumentVersion
    doc_version = DocumentVersion(
        document_id=document.id,
        version_number=version,
        file_path=file_path,
        file_size_bytes=len(file_bytes),
    )
    db.add(doc_version)

    # Parse and chunk document
    sections = parse_document(file_bytes, file.filename or "file.txt")
    embeddings_service = get_embeddings_provider()

    all_chunks = []
    chunk_counter = 0
    for sec in sections:
        chunks = chunk_text(
            text=sec.content,
            page_reference=sec.page_reference,
            section_reference=sec.section_reference,
            start_chunk_index=chunk_counter,
        )
        all_chunks.extend(chunks)
        chunk_counter += len(chunks)

    # Embed and save chunks
    for chunk_payload in all_chunks:
        vector = await embeddings_service.embed_query(chunk_payload.content)
        chunk_entity = DocumentChunk(
            document_id=document.id,
            chunk_index=chunk_payload.chunk_index,
            content=chunk_payload.content,
            embedding=vector,
            page_reference=chunk_payload.page_reference,
            section_reference=chunk_payload.section_reference,
            approval_status_snapshot="approved",
            document_version_snapshot=version,
        )
        db.add(chunk_entity)

    await db.flush()
    await db.refresh(document)
    return document


@router.get("", response_model=list[KnowledgeDocumentRead])
async def list_documents(
    organization_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(KnowledgeDocument)
    if organization_id:
        stmt = stmt.where(KnowledgeDocument.organization_id == organization_id)
    res = await db.execute(stmt)
    return list(res.scalars().all())
