import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    DocumentChunk,
    DocumentVersion,
    KnowledgeDocument,
    Organization,
    User,
)
from src.rag.embeddings import get_embeddings_provider

DEFAULT_ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEFAULT_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def seed_demo_data(db: AsyncSession):
    """
    Seeds initial realistic demo fixtures for local development and testing.
    """
    # 1. Organization
    org = Organization(
        id=DEFAULT_ORG_ID,
        name="Acme SaaS Solutions",
        slug="acme-saas",
    )
    db.add(org)

    # 2. User
    user = User(
        id=DEFAULT_USER_ID,
        organization_id=org.id,
        email="security@acme.com",
        full_name="Security Lead",
        role="admin",
    )
    db.add(user)

    # 3. Approved Security Policy
    policy_content = """
# Acme SaaS Security Policy 2026

## 1. Data Encryption
All customer data at rest is encrypted using AES-256 algorithm with AWS KMS managed keys.
All data in transit is encrypted using TLS 1.3 encryption protocols.

## 2. Access Control & Authentication
Acme SaaS supports SSO via SAML 2.0 and OIDC protocols (Okta, Azure AD, Google Workspace).
Multi-Factor Authentication (MFA) is strictly enforced for all employees.

## 3. Incident Response
Our Security Incident Response Plan guarantees notification within 24 hours of confirmation.
    """.strip()

    doc_id = uuid.uuid4()
    content_hash = hashlib.sha256(policy_content.encode("utf-8")).hexdigest()

    doc = KnowledgeDocument(
        id=doc_id,
        organization_id=org.id,
        title="Acme Security Policy 2026",
        document_type="policy",
        owner_team="Security",
        approval_status="approved",
        version="v2.1",
        content_hash=content_hash,
    )
    db.add(doc)

    doc_ver = DocumentVersion(
        document_id=doc.id,
        version_number="v2.1",
        file_path="virtual://policy_2026.md",
        file_size_bytes=len(policy_content),
    )
    db.add(doc_ver)

    # Chunking & Embeddings
    embeddings = get_embeddings_provider()
    sections = policy_content.split("\n\n")

    for idx, sec in enumerate(sections):
        sec_text = sec.strip()
        if not sec_text:
            continue
        vector = await embeddings.embed_query(sec_text)
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=idx,
            content=sec_text,
            embedding=vector,
            page_reference="Page 1",
            section_reference="Policy Section",
            approval_status_snapshot="approved",
            document_version_snapshot="v2.1",
        )
        db.add(chunk)

    await db.commit()
