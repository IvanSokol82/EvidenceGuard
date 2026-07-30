from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class OrganizationBase(BaseModel):
    name: str
    slug: str


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationRead(OrganizationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "reviewer"


class UserCreate(UserBase):
    organization_id: UUID


class UserRead(UserBase):
    id: UUID
    organization_id: UUID
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeDocumentBase(BaseModel):
    title: str
    document_type: str
    owner_team: str
    approval_status: str = "approved"
    version: str = "v1.0"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    sensitivity_level: str = "internal"
    source_uri: Optional[str] = None


class KnowledgeDocumentCreate(KnowledgeDocumentBase):
    organization_id: UUID
    content_hash: str


class KnowledgeDocumentRead(KnowledgeDocumentBase):
    id: UUID
    organization_id: UUID
    content_hash: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuestionnaireBase(BaseModel):
    title: str
    source_type: str
    output_language: str = "uk"


class QuestionnaireCreate(QuestionnaireBase):
    organization_id: UUID
    original_filename: Optional[str] = None


class QuestionnaireRead(QuestionnaireBase):
    id: UUID
    organization_id: UUID
    original_filename: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuestionRead(BaseModel):
    id: UUID
    questionnaire_id: UUID
    question_number: int
    original_text: str
    normalized_text: Optional[str]
    risk_level: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnswerDraftRead(BaseModel):
    id: UUID
    question_id: UUID
    draft_text: str
    facts: list[str]
    assumptions: list[str]
    missing_information: list[str]
    validation_status: str
    model_name: str
    version: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewDecisionCreate(BaseModel):
    decision: str  # approved, edited, rejected, escalated
    edited_text: Optional[str] = None
    comments: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    database: str
