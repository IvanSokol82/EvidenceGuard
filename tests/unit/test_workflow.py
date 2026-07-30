import pytest

from src.workflow.graph import create_questionnaire_graph
from src.workflow.nodes import route_validation_result, validate_answer_node
from src.workflow.state import QuestionnaireWorkflowState


@pytest.mark.asyncio
async def test_langgraph_workflow_execution():
    graph = create_questionnaire_graph()
    initial_state: QuestionnaireWorkflowState = {
        "questionnaire_id": "test-q1",
        "organization_id": "test-org1",
        "input_document_id": None,
        "raw_content": "1. Do you encrypt customer data at rest using AES-256?\n2. Do you hold SOC 2 certification?",
        "source_type": "pasted",
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

    config = {"configurable": {"thread_id": "test-thread-1"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    assert final_state["status"] == "ready_for_review"
    assert len(final_state["report_items"]) >= 1
    assert "email_draft" in final_state["audit_context"]


def test_conditional_routing_logic():
    state_supported: QuestionnaireWorkflowState = {
        "validation_result": {"status": "SUPPORTED", "is_valid": True},
        "retry_count": 0,
    }
    assert route_validation_result(state_supported) == "append_response"

    state_no_evidence: QuestionnaireWorkflowState = {
        "validation_result": {"status": "NO_EVIDENCE", "is_valid": False},
        "retry_count": 0,
    }
    assert route_validation_result(state_no_evidence) == "create_escalation"

    state_high_risk: QuestionnaireWorkflowState = {
        "validation_result": {"status": "HIGH_RISK_CLAIM", "is_valid": False},
        "retry_count": 0,
    }
    assert route_validation_result(state_high_risk) == "create_escalation"


@pytest.mark.asyncio
async def test_hallucination_guard_certificate_validation():
    # If question asks for SOC 2 certification but evidence pack has no certificate document_type
    state: QuestionnaireWorkflowState = {
        "current_question": {"text": "Do you hold a valid SOC 2 Type II certification?"},
        "evidence_pack": [
            {
                "document_title": "Architecture Overview",
                "document_type": "architecture",  # Not a certificate
                "content": "Hosted on AWS.",
            }
        ],
        "draft_answer": {
            "draft_text": "Yes, we are SOC 2 certified.",
            "validation_status": "SUPPORTED",
        },
    }

    val_res = await validate_answer_node(state)
    assert val_res["validation_result"]["status"] == "HIGH_RISK_CLAIM"
    assert val_res["validation_result"]["is_valid"] is False
