from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.workflow.nodes import (
    append_response_node,
    build_evidence_pack_node,
    build_retrieval_query_node,
    classify_question_node,
    compose_email_draft_node,
    create_escalation_node,
    draft_answer_node,
    extract_content_node,
    extract_questions_node,
    hybrid_retrieve_node,
    normalize_question_node,
    persist_results_node,
    route_next_question,
    route_validation_result,
    validate_answer_node,
    validate_input_node,
)
from src.workflow.state import QuestionnaireWorkflowState


def create_questionnaire_graph():
    """
    Constructs and compiles the EvidenceGuard Questionnaire Processing Graph.
    
    LangGraph Concepts Applied:
    1. StateGraph typed by QuestionnaireWorkflowState.
    2. Explicit node registration with async execution.
    3. Hybrid RAG retrieval node for evidence collection.
    4. Conditional edges for hallucination guard validation routing.
    5. Questionnaire processing loop over extracted_questions.
    6. Stateful checkpointer enabling Human-in-the-Loop workflow pause/resume.
    """
    workflow = StateGraph(QuestionnaireWorkflowState)

    # 1. Add Nodes
    workflow.add_node("validate_input", validate_input_node)
    workflow.add_node("extract_content", extract_content_node)
    workflow.add_node("extract_questions", extract_questions_node)
    workflow.add_node("classify_question", classify_question_node)
    workflow.add_node("normalize_question", normalize_question_node)
    workflow.add_node("build_retrieval_query", build_retrieval_query_node)
    workflow.add_node("hybrid_retrieve", hybrid_retrieve_node)
    workflow.add_node("build_evidence_pack", build_evidence_pack_node)
    workflow.add_node("draft_answer", draft_answer_node)
    workflow.add_node("validate_answer", validate_answer_node)
    workflow.add_node("create_escalation", create_escalation_node)
    workflow.add_node("append_response", append_response_node)
    workflow.add_node("compose_email_draft", compose_email_draft_node)
    workflow.add_node("persist_results", persist_results_node)

    # 2. Add Linear Transitions
    workflow.add_edge(START, "validate_input")
    workflow.add_edge("validate_input", "extract_content")
    workflow.add_edge("extract_content", "extract_questions")
    workflow.add_edge("extract_questions", "classify_question")
    workflow.add_edge("classify_question", "normalize_question")
    workflow.add_edge("normalize_question", "build_retrieval_query")
    workflow.add_edge("build_retrieval_query", "hybrid_retrieve")
    workflow.add_edge("hybrid_retrieve", "build_evidence_pack")
    workflow.add_edge("build_evidence_pack", "draft_answer")
    workflow.add_edge("draft_answer", "validate_answer")


    # 3. Add Conditional Routing Edge for Validation Result
    workflow.add_conditional_edges(
        "validate_answer",
        route_validation_result,
        {
            "append_response": "append_response",
            "create_escalation": "create_escalation",
            "retry_draft": "draft_answer",
        },
    )

    workflow.add_edge("create_escalation", "append_response")

    # 4. Add Conditional Routing Edge for Processing Next Question Loop
    workflow.add_conditional_edges(
        "append_response",
        route_next_question,
        {
            "next_question": "classify_question",
            "finish": "compose_email_draft",
        },
    )

    workflow.add_edge("compose_email_draft", "persist_results")
    workflow.add_edge("persist_results", END)


    # Memory Checkpointer for state resumption & human review pause
    checkpointer = MemorySaver()
    app_graph = workflow.compile(checkpointer=checkpointer)
    return app_graph
