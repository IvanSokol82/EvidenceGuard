import hashlib
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.routes.documents import router as documents_router
from src.api.routes.exports import router as exports_router
from src.api.routes.questionnaires import router as questionnaires_router
from src.api.routes.review import router as review_router
from src.config import settings
from src.database.fixtures import seed_demo_data
from src.database.models import AnswerDraft, DocumentChunk, KnowledgeDocument, Questionnaire, QuestionnaireQuestion
from src.database.session import (
    Base,
    SqliteAsyncSessionLocal,
    engine,
    get_db_session,
    sqlite_engine,
)
from src.rag.embeddings import get_embeddings_provider
from src.rag.parser import parse_document
from src.schemas.models import HealthResponse
from src.ui_templates import templates
from src.workflow.graph import create_questionnaire_graph
from src.workflow.state import QuestionnaireWorkflowState

DEFAULT_ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Attempt PostgreSQL, fallback to SQLite if PostgreSQL is offline
    active_engine = engine
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        print("[Notice] PostgreSQL offline. Falling back to local SQLite database (evidenceguard_dev.db)...")
        active_engine = sqlite_engine
        import src.database.session as session_module
        session_module.current_session_factory = SqliteAsyncSessionLocal
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Seed initial demo data for local exploration
        async with SqliteAsyncSessionLocal() as session:
            try:
                await seed_demo_data(session)
            except Exception:
                pass

    yield

    # Shutdown
    await active_engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="Evidence-backed security answers, with human approval before sending.",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.include_router(documents_router)
app.include_router(questionnaires_router)
app.include_router(review_router)
app.include_router(exports_router)


@app.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db_session)):
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        version="0.1.0",
        database=db_status,
    )


@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request, lang: str = "uk"):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"lang": lang},
    )


@app.get("/ui/documents", response_class=HTMLResponse)
async def ui_documents_page(
    request: Request,
    lang: str = "uk",
    msg: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    res = await db.execute(stmt)
    documents = res.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="documents.html",
        context={
            "documents": documents,
            "default_org_id": str(DEFAULT_ORG_ID),
            "lang": lang,
            "msg": msg,
        },
    )


@app.post("/ui/documents/upload")
async def ui_upload_document(
    organization_id: uuid.UUID = Form(...),
    title: str = Form(...),
    document_type: str = Form(...),
    owner_team: str = Form(...),
    version: str = Form("v1.0"),
    file: UploadFile = File(...),
    lang: str = "uk",
    db: AsyncSession = Depends(get_db_session),
):
    file_bytes = await file.read()
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Check for duplicate document
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.content_hash == content_hash)
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        return RedirectResponse(
            url=f"/ui/documents?msg=duplicate&lang={lang}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    parsed_sections = parse_document(file_bytes, file.filename or "uploaded_doc.txt")
    doc = KnowledgeDocument(
        id=uuid.uuid4(),
        organization_id=organization_id,
        title=title,
        document_type=document_type,
        owner_team=owner_team,
        version=version,
        approval_status="approved",
        content_hash=content_hash,
        source_uri=file.filename,
    )
    db.add(doc)
    await db.flush()

    embeddings = get_embeddings_provider()
    for idx, sec in enumerate(parsed_sections):
        vec = await embeddings.embed_query(sec.content)
        chunk = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            chunk_index=idx,
            content=sec.content,
            embedding=vec,
            page_reference=sec.page_reference or f"Section {idx + 1}",
            section_reference=sec.section_reference or doc.title,
            approval_status_snapshot=doc.approval_status,
            document_version_snapshot=doc.version,
        )
        db.add(chunk)

    await db.commit()

    return RedirectResponse(
        url=f"/ui/documents?msg=success&lang={lang}",
        status_code=status.HTTP_303_SEE_OTHER,
    )




@app.get("/ui/questionnaires/new", response_class=HTMLResponse)

async def ui_new_questionnaire_page(request: Request, lang: str = "uk"):
    return templates.TemplateResponse(
        request=request,
        name="questionnaires_new.html",
        context={
            "default_org_id": str(DEFAULT_ORG_ID),
            "lang": lang,
        },
    )


@app.post("/ui/questionnaires/submit")
async def ui_submit_questionnaire(
    organization_id: uuid.UUID = Form(...),
    title: str = Form(...),
    output_language: str = Form("uk"),
    raw_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    lang: str = "uk",
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

    return RedirectResponse(
        url=f"/ui/questionnaires/{questionnaire.id}?lang={lang}",
        status_code=status.HTTP_303_SEE_OTHER,
    )



@app.get("/ui/questionnaires/{questionnaire_id}", response_class=HTMLResponse)
async def ui_questionnaire_detail_page(
    questionnaire_id: uuid.UUID,
    request: Request,
    lang: str = "uk",
    db: AsyncSession = Depends(get_db_session),
):
    q_stmt = select(Questionnaire).where(Questionnaire.id == questionnaire_id)
    q_res = await db.execute(q_stmt)
    q = q_res.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    qs_stmt = (
        select(QuestionnaireQuestion)
        .where(QuestionnaireQuestion.questionnaire_id == questionnaire_id)
        .options(selectinload(QuestionnaireQuestion.draft_answers))
        .order_by(QuestionnaireQuestion.question_number.asc())
    )
    qs_res = await db.execute(qs_stmt)
    questions = qs_res.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="questionnaire_detail.html",
        context={
            "questionnaire": q,
            "questions": questions,
            "lang": lang,
        },
    )

