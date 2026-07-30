import uuid

from src.schemas.models import (
    KnowledgeDocumentCreate,
    OrganizationCreate,
    QuestionnaireCreate,
)


def test_pydantic_schemas_instantiation():
    org_id = uuid.uuid4()
    org_create = OrganizationCreate(name="Acme Corp", slug="acme")
    assert org_create.name == "Acme Corp"
    assert org_create.slug == "acme"

    doc_create = KnowledgeDocumentCreate(
        organization_id=org_id,
        title="Security Policy 2026",
        document_type="policy",
        owner_team="Security",
        approval_status="approved",
        version="v1.0",
        sensitivity_level="internal",
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert doc_create.title == "Security Policy 2026"
    assert doc_create.approval_status == "approved"

    quest_create = QuestionnaireCreate(
        organization_id=org_id,
        title="Vendor Risk Assessment - Acme",
        source_type="docx",
        output_language="uk",
    )
    assert quest_create.source_type == "docx"
    assert quest_create.output_language == "uk"
