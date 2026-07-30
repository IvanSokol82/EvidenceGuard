import asyncio
import hashlib
import uuid

from sqlalchemy import select

from src.database.models import (
    AnswerDraft,
    DocumentChunk,
    KnowledgeDocument,
    Organization,
    Questionnaire,
    QuestionnaireQuestion,
    User,
)
from src.database.session import (
    AsyncSessionLocal,
    Base,
    SqliteAsyncSessionLocal,
    engine,
    sqlite_engine,
)
from src.rag.embeddings import get_embeddings_provider

DEFAULT_ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEFAULT_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def main():
    print("[Seeding] Seeding realistic test data for EvidenceGuard...")

    session_factory = AsyncSessionLocal
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        print("[Notice] PostgreSQL offline. Seeding into local SQLite database (evidenceguard_db_v2.db)...")
        session_factory = SqliteAsyncSessionLocal
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        # Check existing Organization
        stmt = select(Organization).where(Organization.id == DEFAULT_ORG_ID)
        res = await db.execute(stmt)
        existing_org = res.scalar_one_or_none()

        if not existing_org:
            org = Organization(
                id=DEFAULT_ORG_ID,
                name="Acme Enterprise SaaS Inc.",
                slug="acme-enterprise",
            )
            db.add(org)

            user = User(
                id=DEFAULT_USER_ID,
                organization_id=org.id,
                email="ciso@acme.com",
                full_name="Alex Rivera (CISO)",
                role="admin",
            )
            db.add(user)
            await db.flush()
        else:
            org = existing_org


        # 2. Approved Knowledge Document 1: Security & Encryption Policy 2026
        doc1_content = """
# Acme SaaS Information Security Policy 2026

## Section 1: Data Encryption Standards
- Data at Rest: All customer data, databases, and backup snapshots at rest are strictly encrypted using AES-256 bit encryption via AWS KMS customer-managed keys.
- Data in Transit: All data transferred over public networks is encrypted using TLS 1.3 with strong cipher suites (ECDHE-RSA-AES128-GCM-SHA256).

## Section 2: Identity & Access Management (IAM)
- Single Sign-On (SSO): Acme SaaS natively supports enterprise SSO integration using SAML 2.0 and OpenID Connect (OIDC) protocols (Okta, Azure AD, PingIdentity).
- Multi-Factor Authentication: MFA is mandatorily enforced for all internal personnel accessing production systems.

## Section 3: Business Continuity & Disaster Recovery
- Recovery Point Objective (RPO): Our target RPO is <= 15 minutes with continuous WAL archiving.
- Recovery Time Objective (RTO): Our target RTO is <= 1 hour for full infrastructure failover.
- Incident Notification SLA: In the event of a confirmed security incident, affected customers will be notified within 24 hours.
        """.strip()

        doc1_id = uuid.uuid4()
        hash1 = hashlib.sha256(doc1_content.encode("utf-8")).hexdigest()

        doc1 = KnowledgeDocument(
            id=doc1_id,
            organization_id=org.id,
            title="Information Security Policy 2026",
            document_type="policy",
            owner_team="Security",
            approval_status="approved",
            version="v2026.1",
            content_hash=hash1,
            source_uri="docs/policies/security_policy_2026.md",
        )
        db.add(doc1)

        # 3. Approved Knowledge Document 2: Cloud Infrastructure & Data Residency
        doc2_content = """
# Acme Infrastructure Blueprint & Data Residency

## Data Center Locations & Hosting
- Primary Data Center: AWS Frankfurt Region (eu-central-1), Germany.
- Secondary Failover Region: AWS Ireland Region (eu-west-1), Ireland.
- Data Residency Guarantee: All customer primary databases and backups remain exclusively within the European Union (EU).

## Subprocessors & AI Training Policy
- Subprocessors: Production databases are hosted on AWS RDS PostgreSQL.
- Third-Party AI Models: Customer data is NEVER sent to third-party AI models or used for LLM training without explicit written consent.
        """.strip()

        doc2_id = uuid.uuid4()
        hash2 = hashlib.sha256(doc2_content.encode("utf-8")).hexdigest()

        doc2 = KnowledgeDocument(
            id=doc2_id,
            organization_id=org.id,
            title="Cloud Infrastructure & Data Residency Blueprint",
            document_type="architecture",
            owner_team="Infrastructure",
            approval_status="approved",
            version="v3.0",
            content_hash=hash2,
            source_uri="docs/architecture/cloud_blueprint.md",
        )
        db.add(doc2)
        await db.flush()

        # Chunking & Embeddings
        embeddings = get_embeddings_provider()
        
        for doc_obj, text in [(doc1, doc1_content), (doc2, doc2_content)]:
            sections = text.split("\n\n")
            for idx, sec in enumerate(sections):
                if not sec.strip():
                    continue
                vec = await embeddings.embed_query(sec.strip())
                chunk = DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=doc_obj.id,
                    chunk_index=idx,
                    content=sec.strip(),
                    embedding=vec,
                    page_reference=f"Section {idx + 1}",
                    section_reference=doc_obj.title,
                    approval_status_snapshot="approved",
                    document_version_snapshot=doc_obj.version,
                )
                db.add(chunk)

        # 4. Create Sample Questionnaire
        q_container = Questionnaire(
            id=uuid.uuid4(),
            organization_id=org.id,
            title="Enterprise Vendor Assessment — Financial Corp",
            source_type="docx",
            original_filename="Vendor_Security_Assessment_2026.docx",
            status="ready_for_review",
            output_language="uk",
        )
        db.add(q_container)
        await db.flush()

        # Question 1: Encryption
        q1 = QuestionnaireQuestion(
            id=uuid.uuid4(),
            questionnaire_id=q_container.id,
            question_number=1,
            original_text="Do you encrypt customer data at rest and in transit? Specify the algorithms used.",
            normalized_text="Do you encrypt customer data at rest and in transit AES-256 TLS 1.3",
            risk_level="high",
            status="pending",
        )
        db.add(q1)

        d1 = AnswerDraft(
            id=uuid.uuid4(),
            question_id=q1.id,
            draft_text="Так, усі дані клієнтів у стані спокою шифруються за допомогою стандарту AES-256 із керуванням ключами через AWS KMS. Передача даних здійснюється виключно через протокол TLS 1.3.",
            facts=["Шифрування даних у стані спокою методом AES-256 підтверджено.", "Шифрування у передачі протоколом TLS 1.3 підтверджено."],
            assumptions=[],
            missing_information=[],
            validation_status="SUPPORTED",
            model_name="EvidenceGuard-Copilot",
            version=1,
        )
        db.add(d1)

        # Question 2: SOC 2 Certification (No cert in KB -> Hallucination Guard Flagged)
        q2 = QuestionnaireQuestion(
            id=uuid.uuid4(),
            questionnaire_id=q_container.id,
            question_number=2,
            original_text="Do you hold a valid SOC 2 Type II certification? Attach the report.",
            normalized_text="Do you hold a valid SOC 2 Type II certification",
            risk_level="critical",
            status="escalated",
        )
        db.add(q2)

        d2 = AnswerDraft(
            id=uuid.uuid4(),
            question_id=q2.id,
            draft_text="Статус: NEEDS_HUMAN_INPUT\n\nПричина:\nЗатверджений сертифікат SOC 2 Type II відсутній у базі знань компанії.\n\nРекомендована дія:\nЗавантажити офіційний звіт про аудит у розділі 'База знань' або ескалювати на відділ комплаєнсу.",
            facts=[],
            assumptions=[],
            missing_information=["Офіційний документ/сертифікат SOC 2 відсутній у базі знань."],
            validation_status="HIGH_RISK_CLAIM",
            model_name="EvidenceGuard-GuardEngine",
            version=1,
        )
        db.add(d2)

        await db.commit()
        print("[Success] Demo test data successfully seeded!")



if __name__ == "__main__":
    asyncio.run(main())
