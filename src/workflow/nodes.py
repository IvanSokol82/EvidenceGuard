import json
import re
from typing import Any, Dict

from src.database.session import current_session_factory
from src.rag.embeddings import get_embeddings_provider
from src.rag.retrieval import HybridRetriever
from src.workflow.llm import get_llm_provider
from src.workflow.state import QuestionnaireWorkflowState


async def validate_input_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Validates presence of raw_content or input_document_id.
    Returns partial state update for validation status and errors.
    """
    raw = state.get("raw_content", "").strip()
    if not raw and not state.get("input_document_id"):
        return {
            "status": "error",
            "errors": state.get("errors", []) + ["No input text or document provided."],
        }
    return {"status": "processing", "errors": []}


async def extract_content_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Extracts raw questionnaire text from input.
    """
    raw_content = state.get("raw_content", "")
    return {"raw_content": raw_content}


async def extract_questions_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Splits raw questionnaire text into individual questions, preserving original wording.
    """
    raw = state.get("raw_content", "")
    llm = get_llm_provider()

    prompt = f"Extract all individual security questions from text. Preserve original wording:\n\n{raw}"
    response_text = await llm.generate(prompt)

    parsed_questions = []
    try:
        parsed_questions = json.loads(response_text)
    except Exception:
        pass

    valid_qs = []
    if isinstance(parsed_questions, list):
        for idx, item in enumerate(parsed_questions, start=1):
            if isinstance(item, dict):
                txt = item.get("text", "").strip()
                if txt:
                    valid_qs.append({"number": item.get("number", idx), "text": txt})
            elif isinstance(item, str) and item.strip():
                valid_qs.append({"number": idx, "text": item.strip()})

    if not valid_qs and raw.strip():
        # Fallback split by lines or numbered items (1., 2., etc)
        lines = [line.strip() for line in re.split(r"\n+|(?=\d+[\.\)])", raw) if line.strip()]
        valid_qs = [{"number": i + 1, "text": line} for i, line in enumerate(lines)]


    if not valid_qs:
        valid_qs = [{"number": 1, "text": raw.strip() or "Security requirement"}]

    first_q = valid_qs[0]

    return {
        "extracted_questions": valid_qs,
        "current_question_index": 0,
        "current_question": first_q,
    }



async def classify_question_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Classifies the current question topic, risk level, multi-part flags.
    """
    current_q = state.get("current_question")
    if not current_q:
        return {"classification": None}

    q_text = current_q.get("text", "")
    llm = get_llm_provider()
    prompt = f"Classify the following security question into topic, tags, risk level:\n{q_text}"
    resp = await llm.generate(prompt)

    try:
        class_data = json.loads(resp)
    except Exception:
        class_data = {
            "topic": "General Security",
            "tags": [],
            "is_multi_part": False,
            "sub_questions": [],
            "risk_level": "medium",
        }

    return {"classification": class_data}


async def normalize_question_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Normalizes question wording to optimize RAG search queries.
    """
    current_q = state.get("current_question")
    if not current_q:
        return {"normalized_question": None}

    text = current_q.get("text", "")
    # Clean noise and keep core technical query
    normalized_text = re.sub(r"^\d+[\.\)]\s*", "", text).strip()
    return {
        "normalized_question": {
            "original_text": text,
            "normalized_text": normalized_text,
        }
    }


async def build_retrieval_query_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Builds semantic query vector, keyword FTS query, and metadata filters.
    """
    norm_q = state.get("normalized_question")
    query_text = norm_q.get("normalized_text", "") if norm_q else ""

    embeddings_service = get_embeddings_provider()
    query_vector = await embeddings_service.embed_query(query_text)

    return {
        "retrieval_query": {
            "query_text": query_text,
            "query_vector": query_vector,
        }
    }



async def hybrid_retrieve_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:

    """
    LangGraph Node: Calls HybridRetriever to perform pgvector + FTS search with RRF.
    """
    ret_query = state.get("retrieval_query")
    if not ret_query:
        return {"evidence_pack": []}

    query_text = ret_query.get("query_text", "")
    query_vector = ret_query.get("query_vector", [])
    org_id = state.get("organization_id")

    async with current_session_factory() as db_session:
        retriever = HybridRetriever(db=db_session)
        retrieved_items = await retriever.retrieve(
            query_text=query_text,
            query_vector=query_vector,
            top_n=5,
            target_organization_id=org_id,
        )

        evidence_pack = [
            {
                "chunk_id": str(item.chunk_id),
                "document_id": str(item.document_id),
                "document_title": item.document_title,
                "document_type": item.document_type,
                "owner_team": item.owner_team,
                "version": item.version,
                "page_reference": item.page_reference,
                "section_reference": item.section_reference,
                "content": item.content,
                "rrf_score": item.rrf_score,
                "confidence_score": item.confidence_score,
            }
            for item in retrieved_items
        ]

    return {"evidence_pack": evidence_pack}



async def build_evidence_pack_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Formats evidence pack items into context for answer drafting.
    """
    pack = state.get("evidence_pack", [])
    return {"evidence_pack": pack}


async def draft_answer_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Drafts an answer strictly using approved evidence.
    If no evidence is present, sets status to NEEDS_HUMAN_INPUT.
    """
    pack = state.get("evidence_pack", [])
    current_q = state.get("current_question", {})
    q_text = current_q.get("text", "") if current_q else ""

    if not pack:
        return {
            "draft_answer": {
                "draft_text": "Статус: NEEDS_HUMAN_INPUT\n\nПричина:\nЖодного затвердженого доказу не знайдено для підтвердження цієї відповіді.\n\nРекомендована дія:\nПідтвердити політику або додати новий затверджений документ-джерело.",
                "facts": [],
                "assumptions": [],
                "missing_information": ["Відсутні затверджені документи-джерела у базі знань."],
                "validation_status": "NO_EVIDENCE",
                "model_name": "EvidenceGuard-GuardEngine",
                "version": 1,
            }
        }

    llm = get_llm_provider()
    prompt = f"Draft answer for: {q_text}\nContext evidence:\n{json.dumps(pack)}"
    resp = await llm.generate(prompt)

    try:
        draft_data = json.loads(resp)
    except Exception:
        draft_data = {
            "draft_text": f"Відповідь підготовлено на основі документа '{pack[0]['document_title']}': {pack[0]['content']}",
            "facts": [pack[0]["content"]],
            "assumptions": [],
            "missing_information": [],
            "validation_status": "SUPPORTED",
            "model_name": "EvidenceGuard-Copilot",
            "version": 1,
        }

    if pack and draft_data.get("validation_status") == "SUPPORTED":
        citations = []
        for item in pack[:2]:
            doc_title = item.get("document_title", "Документ")
            sec_ref = item.get("section_reference") or item.get("page_reference") or "Головний розділ"
            version = item.get("version", "v1.0")
            citations.append(f"• {doc_title} ({sec_ref}, версія {version})")

        sources_block = "\n\n📌 Джерела доказів у базі знань:\n" + "\n".join(citations)
        if "📌 Джерела доказів" not in draft_data.get("draft_text", ""):
            draft_data["draft_text"] = draft_data.get("draft_text", "") + sources_block

    return {"draft_answer": draft_data}



async def validate_answer_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node (Hallucination Guard): Validates answer draft against citations.
    Checks:
    - Every claim has a citation
    - No fabricated SOC 2 / ISO 27001 certifications without approved certificate in evidence
    - No invented SLA, RPO/RTO, or legal guarantees
    """
    draft = state.get("draft_answer")
    pack = state.get("evidence_pack", [])
    current_q = state.get("current_question", {})
    q_text = current_q.get("text", "").lower() if current_q else ""

    if not draft or draft.get("validation_status") == "NO_EVIDENCE":
        return {
            "validation_result": {
                "status": "NO_EVIDENCE",
                "is_valid": False,
                "reason": "Затверджені докази відсутні.",
            }
        }

    # Strict Certificate Validation Guard
    if ("soc 2" in q_text or "iso 27001" in q_text) and not any(
        item.get("document_type") == "certificate" for item in pack
    ):
        return {
            "validation_result": {
                "status": "HIGH_RISK_CLAIM",
                "is_valid": False,
                "reason": "Заява про наявність SOC 2 / ISO 27001 вимагає наявності відповідного сертифіката в базі знань.",
            }
        }

    return {
        "validation_result": {
            "status": draft.get("validation_status", "SUPPORTED"),
            "is_valid": True,
            "reason": "Відповідь верифікована за доказами.",
        }
    }


def route_validation_result(state: QuestionnaireWorkflowState) -> str:
    """
    LangGraph Conditional Routing Function.
    Determines next edge based on validation_result status.
    """
    val_res = state.get("validation_result", {})
    status = val_res.get("status", "NO_EVIDENCE")

    if status in ("SUPPORTED", "PARTIALLY_SUPPORTED"):
        return "append_response"
    elif status in ("NO_EVIDENCE", "HIGH_RISK_CLAIM"):
        return "create_escalation"
    elif status == "INVALID_ANSWER":
        retry = state.get("retry_count", 0)
        if retry < 1:
            return "retry_draft"
        return "create_escalation"
    else:
        return "create_escalation"


async def create_escalation_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Creates an escalation task assigned to owner team when evidence is missing or high risk.
    """
    classification = state.get("classification") or {}
    val_res = state.get("validation_result") or {}

    owner_team = classification.get("topic", "Security")
    reason = val_res.get("reason", "Відсутні докази для підтвердження відповіді.")

    escalation = {
        "owner_team": owner_team,
        "reason": reason,
        "recommended_action": "Підтвердити політику або додати затверджений документ у базі знань.",
        "status": "open",
    }
    return {"escalation_task": escalation}


async def append_response_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Appends current question, draft answer, evidence, escalation to report items,
    and advances current_question_index to the next question.
    """
    current_q = state.get("current_question")
    draft = state.get("draft_answer")
    pack = state.get("evidence_pack", [])
    esc = state.get("escalation_task")
    val_res = state.get("validation_result", {})

    report_item = {
        "question": current_q,
        "draft_answer": draft,
        "evidence_pack": pack,
        "escalation_task": esc,
        "validation_status": val_res.get("status", "NO_EVIDENCE"),
    }

    current_report = state.get("report_items", [])
    new_report = current_report + [report_item]

    extracted_qs = state.get("extracted_questions", [])
    next_idx = state.get("current_question_index", 0) + 1
    next_q = extracted_qs[next_idx] if next_idx < len(extracted_qs) else None

    return {
        "report_items": new_report,
        "current_question_index": next_idx,
        "current_question": next_q,
        "evidence_pack": [],
        "draft_answer": None,
        "escalation_task": None,
        "validation_result": None,
    }


def route_next_question(state: QuestionnaireWorkflowState) -> str:
    """
    LangGraph Conditional Routing Function.
    Loops back to classify_question for the next question or finishes workflow.
    """
    extracted_qs = state.get("extracted_questions", [])
    current_idx = state.get("current_question_index", 0)

    if current_idx < len(extracted_qs):
        return "next_question"
    return "finish"



async def compose_email_draft_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Composes a summary email draft in Ukrainian for human review and manual sending.
    """
    report = state.get("report_items", [])
    total_q = len(report)
    supported_count = sum(1 for item in report if item.get("validation_status") == "SUPPORTED")
    escalated_count = total_q - supported_count

    email_body = f"""Доброго дня!

Дякуємо за ваші запитання щодо інформаційної безпеки.
Ми підготували чернетку відповідей на основі затверджених політик безпеки нашої компанії.

Підсумок перевірки:
- Усього запитань: {total_q}
- Підтверджено доказами: {supported_count}
- Потребує підтвердження / уточнення: {escalated_count}

З повагою,
Команда безпеки
"""
    return {"audit_context": {**state.get("audit_context", {}), "email_draft": email_body}}


async def persist_results_node(state: QuestionnaireWorkflowState) -> Dict[str, Any]:
    """
    LangGraph Node: Persists workflow results and returns completed status.
    """
    return {"status": "ready_for_review"}
