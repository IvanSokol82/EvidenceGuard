from typing import Any, Optional, TypedDict


class QuestionnaireWorkflowState(TypedDict):
    """
    Typed LangGraph workflow state schema for EvidenceGuard security questionnaire pipeline.
    
    LangGraph Concept:
    State is an immutable/versioned dictionary passed between node functions.
    Each node function receives a snapshot of this state and returns only partial state updates.
    """
    questionnaire_id: str
    organization_id: str
    input_document_id: Optional[str]
    raw_content: str
    source_type: str  # pasted, pdf, docx, xlsx, eml
    extracted_questions: list[dict[str, Any]]
    current_question_index: int
    current_question: Optional[dict[str, Any]]
    normalized_question: Optional[dict[str, Any]]
    classification: Optional[dict[str, Any]]
    retrieval_query: Optional[dict[str, Any]]
    evidence_pack: list[dict[str, Any]]
    draft_answer: Optional[dict[str, Any]]
    validation_result: Optional[dict[str, Any]]
    escalation_task: Optional[dict[str, Any]]
    report_items: list[dict[str, Any]]
    status: str  # processing, awaiting_human_review, completed, error
    retry_count: int
    errors: list[str]
    audit_context: dict[str, Any]
