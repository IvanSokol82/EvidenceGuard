import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AnswerDraft, Questionnaire, QuestionnaireQuestion
from src.database.session import get_db_session
from src.rag.parser import parse_document
from src.schemas.models import QuestionnaireRead
from src.workflow.graph import create_questionnaire_graph
from src.workflow.state import QuestionnaireWorkflowState

router = APIRouter(prefix="/questionnaires", tags=["Questionnaires"])


@router.post("/submit", response_model=QuestionnaireRead, status_code=status.HTTP_201_CREATED)
async def submit_questionnaire(
    organization_id: uuid.UUID = Form(...),
    title: str = Form(...),
    output_language: str = Form("uk"),
    raw_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db_session),
):
    if not raw_text and not file:
        raise HTTPException(
            status_code=400, detail="Must provide either raw_text or an uploaded questionnaire file."
        )

    content_str = ""
    source_type = "pasted"
    filename = None

    if file and file.filename and len(file.filename.strip()) > 0:
        file_bytes = await file.read()
        filename = file.filename
        ext = filename.lower().split(".")[-1] if filename and "." in filename else "txt"
        source_type = ext
        parsed_sections = parse_document(file_bytes, filename or "questionnaire.txt")
        content_str = "\n\n".join(sec.content for sec in parsed_sections)
    else:
        content_str = raw_text or ""


    questionnaire = Questionnaire(
        id=uuid.uuid4(),
        organization_id=organization_id,
        title=title,
        source_type=source_type,
        original_filename=filename,
        output_language=output_language,
        status="processing",
    )
    db.add(questionnaire)
    await db.flush()

    # Execute LangGraph Workflow
    graph = create_questionnaire_graph()
    initial_state: QuestionnaireWorkflowState = {
        "questionnaire_id": str(questionnaire.id),
        "organization_id": str(organization_id),
        "input_document_id": None,
        "raw_content": content_str,
        "source_type": source_type,
        "extracted_questions": [],
        "current_question_index": 0,
        "current_question": None,
        "normalized_question": None,
        "classification": None,
        "retrieval_query": None,
        "evidence_pack": [],
        "draft_answer": None,
        "validation_result": None,
        "escalation_task": None,
        "report_items": [],
        "status": "processing",
        "retry_count": 0,
        "errors": [],
        "audit_context": {},
    }

    config = {"configurable": {"thread_id": str(questionnaire.id)}}
    final_state = await graph.ainvoke(initial_state, config=config)

    # Persist extracted questions and drafts to Postgres
    report_items = final_state.get("report_items", [])
    for idx, item in enumerate(report_items, start=1):
        q_info = item.get("question", {})
        draft_info = item.get("draft_answer", {})

        qq = QuestionnaireQuestion(
            id=uuid.uuid4(),
            questionnaire_id=questionnaire.id,
            question_number=idx,
            original_text=q_info.get("text", f"Question {idx}"),
            normalized_text=q_info.get("text"),
            risk_level="medium",
            status="drafted" if draft_info.get("validation_status") == "SUPPORTED" else "escalated",
        )
        db.add(qq)
        await db.flush()

        if draft_info:
            draft_entity = AnswerDraft(
                id=uuid.uuid4(),
                question_id=qq.id,
                draft_text=draft_info.get("draft_text", ""),
                facts=draft_info.get("facts", []),
                assumptions=draft_info.get("assumptions", []),
                missing_information=draft_info.get("missing_information", []),
                validation_status=draft_info.get("validation_status", "NO_EVIDENCE"),
                model_name=draft_info.get("model_name", "EvidenceGuard-Copilot"),
                version=1,
            )
            db.add(draft_entity)

    questionnaire.status = "ready_for_review"
    await db.flush()
    await db.refresh(questionnaire)
    return questionnaire


@router.get("/{questionnaire_id}", response_model=QuestionnaireRead)
async def get_questionnaire(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(Questionnaire).where(Questionnaire.id == questionnaire_id)
    res = await db.execute(stmt)
    q = res.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found.")
    return q
