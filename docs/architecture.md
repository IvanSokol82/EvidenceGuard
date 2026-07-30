# Technical Architecture & System Design: EvidenceGuard

---

## 1. Architectural Summary & Technology Decisions

### Key Technology Stack
- **Language & Runtime:** Python 3.11+ async
- **API Framework:** FastAPI with Pydantic v2
- **Workflow Orchestration:** LangGraph (Stateful, async graph execution with PostgreSQL Checkpointer)
- **Database & Storage:** PostgreSQL 17+ with `pgvector` extension for semantic retrieval and `tsvector` for full-text search
- **ORM & DB Access:** SQLAlchemy 2.0 (asyncio) + `asyncpg` / `psycopg3` async
- **Migrations:** Alembic
- **Testing & Tooling:** `pytest` (async), `Ruff` (linter/formatter), `mypy` / `pyright` (static typing)
- **Local Dev & LLM:** Local-first with Ollama / OpenAI-compatible local endpoints, mockable LLM abstraction for test isolation.
- **Deployment:** Docker & Docker Compose

### Frontend Choice Rationale
**Selected Stack:** FastAPI + Jinja2 Templates + HTMX + Tailwind CSS (bundled via CDN/CLI).
**Why this over React/Next.js for MVP:**
1. **Single Unified Codebase:** Avoids dual-repository build overhead, CORS complexity, and duplicate API type definitions during rapid MVP iteration.
2. **Seamless LangGraph Integration:** HTMX allows real-time async polling of workflow checkpointer state, review queue updates, and evidence inspection directly with server-driven HTML fragments.
3. **Local-First & Lightweight:** Loads fast without heavy node_modules dependencies, simplifying local evaluation and open-source setup.
4. **Native Localization:** Ukrainian UI copy is directly rendered on the server without client-side hydration issues or complex i18n bundle setups.

---

## 2. Mermaid System Architecture Diagram

```mermaid
flowchart TD
    subgraph Client [User Interface - FastAPI + Jinja2 + HTMX]
        UI_Doc[Document Management /documents]
        UI_Quest[Questionnaire Input /questionnaires/new]
        UI_Review[Review Queue /review]
        UI_Export[Export & Email Draft /exports]
    end

    subgraph API [FastAPI Application Layer]
        Router_Doc[Document Router]
        Router_Quest[Questionnaire Router]
        Router_Review[Review Router]
        Auth_Middleware[Basic Auth & Rate Limiter]
    end

    subgraph Workflow [LangGraph Orchestration Engine]
        N_Validate[validate_input_node]
        N_ExtractDoc[extract_content_node]
        N_ExtractQ[extract_questions_node]
        N_Classify[classify_question_node]
        N_Norm[normalize_question_node]
        N_Query[build_retrieval_query_node]
        N_Retrieve[hybrid_retrieve_node]
        N_Pack[build_evidence_pack_node]
        N_Draft[draft_answer_node]
        N_ValidateAns[validate_answer_node]
        N_Route{route_validation_result}
        N_Escalated[create_escalation_node]
        N_Append[append_response_node]
        N_Email[compose_email_draft_node]
        N_Persist[persist_results_node]
    end

    subgraph RAG [Hybrid Retrieval Engine]
        PG_Vector[(pgvector Semantic Search)]
        PG_FTS[(PostgreSQL tsvector FTS)]
        RRF_Fusion[Reciprocal Rank Fusion]
    end

    subgraph DB [(PostgreSQL 17 Database)]
        tbl_docs[KnowledgeDocument & Chunks]
        tbl_quest[Questionnaire & Questions]
        tbl_drafts[AnswerDraft & EvidenceItem]
        tbl_audit[AuditEvent & ReviewDecision]
        tbl_checkpoints[LangGraph Checkpoint Store]
    end

    UI_Doc --> Router_Doc
    UI_Quest --> Router_Quest
    UI_Review --> Router_Review
    UI_Export --> Router_Review

    Router_Doc --> DB
    Router_Quest --> N_Validate

    N_Validate --> N_ExtractDoc --> N_ExtractQ --> N_Classify --> N_Norm --> N_Query
    N_Query --> N_Retrieve
    N_Retrieve --> RAG
    RAG --> PG_Vector & PG_FTS
    PG_Vector & PG_FTS --> RRF_Fusion --> N_Pack
    N_Pack --> N_Draft --> N_ValidateAns --> N_Route

    N_Route -- SUPPORTED / PARTIALLY_SUPPORTED --> N_Append
    N_Route -- NO_EVIDENCE / HIGH_RISK_CLAIM --> N_Escalated --> N_Append
    N_Route -- INVALID_ANSWER (retry once) --> N_Draft

    N_Append --> N_Email --> N_Persist --> tbl_checkpoints
    N_Persist --> DB
```

---

## 3. Database Schema Overview (Entity Relationship)

Key Entities:
1. `Organization`: Multi-team top-level entity.
2. `User`: Admin / Reviewer account.
3. `KnowledgeDocument`: Metadata for uploaded policy / technical document.
4. `DocumentVersion`: Version tracking for documents.
5. `DocumentChunk`: Text chunks with `vector(1536)` embedding and `tsvector` content column.
6. `Questionnaire`: Uploaded/pasted questionnaire container.
7. `QuestionnaireQuestion`: Extracted individual question with classification and risk level.
8. `QuestionClassification`: Topic taxonomy, tags, multi-part flags.
9. `RetrievalRun`: Audit log for RAG execution per question.
10. `EvidenceItem`: Specific retrieved chunk reference with confidence & RRF score.
11. `AnswerDraft`: Drafted response with citations, assumptions, missing info flag.
12. `ReviewDecision`: Human approval, edit, reject, or escalation decision.
13. `EscalationTask`: Task assigned to owner team when evidence is missing or high risk.
14. `AuditEvent`: Audit log entry for system actions.

---

## 4. LangGraph Workflow State & Node Architecture

### State Specification (`QuestionnaireWorkflowState`)
```python
from typing import TypedDict, Any

class QuestionnaireWorkflowState(TypedDict):
    questionnaire_id: str
    organization_id: str
    input_document_id: str | None
    raw_content: str
    extracted_questions: list[dict[str, Any]]
    current_question_id: str | None
    normalized_question: dict[str, Any] | None
    classification: dict[str, Any] | None
    retrieval_query: dict[str, Any] | None
    evidence_pack: list[dict[str, Any]]
    draft_answer: dict[str, Any] | None
    validation_result: dict[str, Any] | None
    escalation_task: dict[str, Any] | None
    report_items: list[dict[str, Any]]
    status: str
    errors: list[str]
    audit_context: dict[str, Any]
```

### Core LangGraph Principles Applied
- **Async Execution:** All node functions defined as `async def`.
- **Immutability & Partial Updates:** Nodes return dictionary slices updating only modified keys.
- **Stateful Checkpointing:** Postgres-backed checkpointer allows execution pause at review steps and resumption after human interaction.
- **Deterministic Hallucination Guard:** Answers are validated against cited evidence before proceeding to review.
