import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import AnswerDraft, Questionnaire, QuestionnaireQuestion
from src.database.session import get_db_session

router = APIRouter(prefix="/exports", tags=["Exports & Output"])


@router.get("/{questionnaire_id}/markdown", response_class=PlainTextResponse)
async def export_questionnaire_markdown(
    questionnaire_id: uuid.UUID,
    lang: str = "uk",
    db: AsyncSession = Depends(get_db_session),
):
    """
    Generates a clean Markdown security response document with citations and warnings in chosen language (uk/en).
    """
    q_stmt = select(Questionnaire).where(Questionnaire.id == questionnaire_id)
    q_res = await db.execute(q_stmt)
    q = q_res.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found.")

    qs_stmt = (
        select(QuestionnaireQuestion)
        .where(QuestionnaireQuestion.questionnaire_id == questionnaire_id)
        .options(selectinload(QuestionnaireQuestion.draft_answers))
        .order_by(QuestionnaireQuestion.question_number.asc())
    )
    qs_res = await db.execute(qs_stmt)
    questions = qs_res.scalars().all()

    is_en = lang.lower() == "en"

    if is_en:
        md_lines = [
            f"# Security Response Report: {q.title}",
            f"**Generated Date:** {q.created_at.strftime('%Y-%m-%d') if q.created_at else 'N/A'}",
            f"**Source Format:** {q.source_type.upper()}",
            f"**Status:** {q.status}",
            "",
            "---",
            "",
            "## Security & Compliance Responses",
            "",
        ]
    else:
        md_lines = [
            f"# Звіт відповідей з безпеки: {q.title}",
            f"**Дата формування:** {q.created_at.strftime('%Y-%m-%d') if q.created_at else 'N/A'}",
            f"**Формат джерела:** {q.source_type.upper()}",
            f"**Статус:** {q.status}",
            "",
            "---",
            "",
            "## Відповіді на запитання з інформаційної безпеки",
            "",
        ]

    for question in questions:
        q_header = f"### Question #{question.question_number}: {question.original_text}" if is_en else f"### Запитання #{question.question_number}: {question.original_text}"
        md_lines.append(q_header)

        drafts = question.draft_answers
        if drafts:
            draft: AnswerDraft = drafts[-1]
            status_label = f"**Validation Status:** `{draft.validation_status}`" if is_en else f"**Статус підтвердження:** `{draft.validation_status}`"
            md_lines.append(status_label)
            md_lines.append("")
            md_lines.append("```text")
            md_lines.append(draft.draft_text)
            md_lines.append("```")
            md_lines.append("")

            if draft.facts:
                md_lines.append("**Verified Facts:**" if is_en else "**Підтверджені факти:**")
                for fact in draft.facts:
                    md_lines.append(f"- {fact}")
                md_lines.append("")

            if draft.missing_information:
                md_lines.append("> [!WARNING]")
                md_lines.append("> **Missing Information in Knowledge Base:**" if is_en else "> **Відсутня інформація в базі знань:**")
                for missing in draft.missing_information:
                    md_lines.append(f"> - {missing}")
                md_lines.append("")
        else:
            md_lines.append("*Draft answer is pending generation.*" if is_en else "*Чернетку відповіді ще не сформовано.*")
            md_lines.append("")

        md_lines.append("---")
        md_lines.append("")

    if is_en:
        md_lines.extend([
            "## Disclaimer",
            "EvidenceGuard prepares evidence-backed security questionnaire drafts.",
            "This document does not constitute legal, compliance, or certification advice.",
            "All responses must be reviewed and approved by an authorized human representative before sending.",
        ])
    else:
        md_lines.extend([
            "## Застереження (Disclaimer)",
            "EvidenceGuard готує чернетки відповідей виключно на основі наданих доказів.",
            "Цей документ не є юридичною консультацією чи сертифікатом.",
            "Усі відповіді підлягають обов'язковій перевірці та затвердженню уповноваженим представником компанії.",
        ])

    return "\n".join(md_lines)


@router.get("/{questionnaire_id}/json")
async def export_questionnaire_json(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Generates a full JSON audit export containing original questions, draft answers, facts, and audit metadata.
    """
    q_stmt = select(Questionnaire).where(Questionnaire.id == questionnaire_id)
    q_res = await db.execute(q_stmt)
    q = q_res.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found.")

    qs_stmt = (
        select(QuestionnaireQuestion)
        .where(QuestionnaireQuestion.questionnaire_id == questionnaire_id)
        .options(selectinload(QuestionnaireQuestion.draft_answers))
        .order_by(QuestionnaireQuestion.question_number.asc())
    )
    qs_res = await db.execute(qs_stmt)
    questions = qs_res.scalars().all()

    export_data: dict[str, Any] = {
        "questionnaire_id": str(q.id),
        "organization_id": str(q.organization_id),
        "title": q.title,
        "source_type": q.source_type,
        "status": q.status,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "questions": [],
    }

    for question in questions:
        q_data = {
            "question_number": question.question_number,
            "original_text": question.original_text,
            "risk_level": question.risk_level,
            "status": question.status,
            "drafts": [],
        }
        for d in question.draft_answers:
            q_data["drafts"].append({
                "draft_id": str(d.id),
                "draft_text": d.draft_text,
                "facts": d.facts,
                "assumptions": d.assumptions,
                "missing_information": d.missing_information,
                "validation_status": d.validation_status,
                "model_name": d.model_name,
                "version": d.version,
            })
        export_data["questions"].append(q_data)

    return JSONResponse(content=export_data)


@router.get("/{questionnaire_id}/email", response_class=PlainTextResponse)
async def export_questionnaire_email_draft(
    questionnaire_id: uuid.UUID,
    lang: str = "uk",
    db: AsyncSession = Depends(get_db_session),
):
    """
    Generates a copyable email draft summary in UK or EN based on ?lang= query param.
    """
    q_stmt = select(Questionnaire).where(Questionnaire.id == questionnaire_id)
    q_res = await db.execute(q_stmt)
    q = q_res.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found.")

    qs_stmt = (
        select(QuestionnaireQuestion)
        .where(QuestionnaireQuestion.questionnaire_id == questionnaire_id)
        .options(selectinload(QuestionnaireQuestion.draft_answers))
    )
    qs_res = await db.execute(qs_stmt)
    questions = qs_res.scalars().all()

    total = len(questions)
    supported = 0
    needs_input = 0

    for question in questions:
        if question.draft_answers and question.draft_answers[-1].validation_status == "SUPPORTED":
            supported += 1
        else:
            needs_input += 1

    is_en = lang.lower() == "en"

    if is_en:
        email_text = f"""Subject: Security Questionnaire Responses — {q.title}

Hello,

Thank you for providing your security questionnaire regarding information security and compliance.
Our security team has prepared evidence-backed responses based on our approved company security policies and infrastructure blueprints.

Assessment Summary:
- Total Questions Processed: {total}
- Fully Supported by Evidence Pack: {supported}
- Pending Human Review / Clarification: {needs_input}

The attached report contains detailed responses along with exact evidence citations.

Best regards,
Information Security Team
"""
    else:
        email_text = f"""Тема: Відповіді на Security Questionnaire — {q.title}

Доброго дня!

Дякуємо за ваші запитання щодо інформаційної безпеки.
Наша команда опрацювала опитувальник на основі затверджених політик безпеки та інфраструктурних документів компанії.

Підсумок опрацювання:
- Усього запитань: {total}
- Підтверджено доказовою базою: {supported}
- Потребують додаткового узгодження: {needs_input}

Сформований звіт із цитуваннями додається у файлі.

З повагою,
Команда інформаційної безпеки
"""
    return email_text
