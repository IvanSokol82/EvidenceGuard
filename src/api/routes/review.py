import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import AnswerDraft, EvidenceItem, QuestionnaireQuestion, ReviewDecision
from src.database.session import get_db_session
from src.ui_templates import templates

router = APIRouter(prefix="/ui/review", tags=["Review Queue UI"])


@router.get("", response_class=HTMLResponse)
async def review_queue_page(
    request: Request,
    lang: str = "uk",
    db: AsyncSession = Depends(get_db_session),
):
    # Fetch drafts that are ready for review
    stmt = (
        select(AnswerDraft)
        .options(
            selectinload(AnswerDraft.question),
            selectinload(AnswerDraft.review_decisions),
        )
        .order_by(AnswerDraft.created_at.desc())
    )
    res = await db.execute(stmt)
    drafts = res.scalars().all()

    queue_items = []
    for d in drafts:
        # Fetch evidence for question
        ev_stmt = select(EvidenceItem).options(selectinload(EvidenceItem.chunk)).limit(4)
        ev_res = await db.execute(ev_stmt)
        evidence_items = ev_res.scalars().all()

        queue_items.append({
            "draft": d,
            "question": d.question,
            "evidence": evidence_items,
        })

    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "queue_items": queue_items,
            "lang": lang,
        },
    )




@router.post("/{draft_id}/decision")
async def record_review_decision(
    draft_id: uuid.UUID,
    decision: str = Form(...),
    edited_text: Optional[str] = Form(None),
    comments: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_session),
):
    draft_stmt = select(AnswerDraft).where(AnswerDraft.id == draft_id)
    draft_res = await db.execute(draft_stmt)
    draft = draft_res.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="Draft answer not found.")

    review_dec = ReviewDecision(
        id=uuid.uuid4(),
        draft_id=draft.id,
        decision=decision,
        edited_text=edited_text if decision == "edited" else None,
        comments=comments,
    )
    db.add(review_dec)

    # Update question status
    q_stmt = select(QuestionnaireQuestion).where(QuestionnaireQuestion.id == draft.question_id)
    q_res = await db.execute(q_stmt)
    question = q_res.scalar_one_or_none()
    if question:
        if decision == "approved":
            question.status = "reviewed"
        elif decision == "edited":
            question.status = "reviewed"
            draft.draft_text = edited_text or draft.draft_text
        elif decision == "escalated":
            question.status = "escalated"
        elif decision == "rejected":
            question.status = "rejected"

    await db.flush()
    return RedirectResponse(url="/ui/review", status_code=status.HTTP_303_SEE_OTHER)
