"""
Conversation orchestration service for procurement follow-up questions.

The service loads the latest saved workflow, resolves conversation memory and
entities, routes the question, builds selective context, generates an answer,
persists the turn, and triggers summarization when required.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from conversation.answer_generator import (
    generate_context_answer,
)
from conversation.context_builder import (
    build_context_from_analysis,
)
from conversation.debug_logger import (
    ConversationTraceLogger,
)
from conversation.entity_index import (
    get_or_build_entity_index,
)
from conversation.models import QueryAnalysis
from conversation.query_analyzer import (
    analyze_user_question,
)
from conversation.summarizer import (
    should_summarize_conversation,
    summarize_conversation,
)
from core.logging import (
    bind_log_context,
    get_logger,
    reset_log_context,
)
from core.observability import (
    build_trace_metadata,
    langsmith_extra as build_langsmith_extra,
    traceable_if_enabled,
)
from persistence import (
    load_latest_conversation_summary,
    load_latest_workflow_run,
    load_messages,
    load_session_activity,
    save_message,
)


CONVERSATION_SERVICE_VERSION = (
    "conversation_service_v8 "
    "| centralized-observability-and-safe-context-loading"
)

logger = get_logger("conversation.service")


class ConversationServiceError(RuntimeError):
    """Raised when the conversation orchestration service cannot complete."""


def _as_dict(
    value: Any,
) -> Dict[str, Any]:
    """
    Return a dictionary from persisted dict or JSON-string values.

    Invalid or unsupported values return an empty dictionary, matching the
    previous service fallback behavior.
    """
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

        return decoded if isinstance(decoded, dict) else {}

    return {}


def load_conversation_memory(
    session_id: str,
    recent_limit: int = 6,
) -> Dict[str, Any]:
    """Load the latest summary and recent persisted messages."""
    latest_summary = (
        load_latest_conversation_summary(
            session_id
        )
    )

    return {
        "summary": (
            latest_summary.get("summary_text")
            if latest_summary
            else None
        ),
        "summary_record": latest_summary,
        "recent_messages": load_messages(
            session_id,
            limit=recent_limit,
        ),
    }


def get_latest_effective_decision(
    session_id: str,
    run_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Return the newest effective plan or override for the selected workflow run.
    """
    for activity in load_session_activity(
        session_id,
        limit=50,
    ):
        if (
            run_id
            and activity.get("run_id") != run_id
        ):
            continue

        details = _as_dict(
            activity.get("details") or {}
        )
        metadata = _as_dict(
            details.get("metadata") or {}
        )

        effective = (
            details.get("effective_decision")
            or details.get("effective_plan")
            or metadata.get("effective_plan")
        )

        if effective:
            return (
                effective
                if isinstance(effective, dict)
                else _as_dict(effective)
            )

    return None


def load_workflow_context(
    session_id: str,
) -> Dict[str, Any]:
    """Load and normalize the latest persisted workflow result."""
    latest_run = load_latest_workflow_run(
        session_id
    )

    if not latest_run:
        return {"has_context": False}

    final_state = _as_dict(
        latest_run.get("final_state")
        or latest_run.get("final_state_json")
        or {}
    )
    decision = _as_dict(
        latest_run.get("decision_aggregation")
        or latest_run.get(
            "decision_aggregation_json"
        )
        or {}
    )
    input_payload = _as_dict(
        latest_run.get("input_payload")
        or latest_run.get("input_payload_json")
        or {}
    )
    run_id = latest_run.get("run_id")

    return {
        "has_context": True,
        "run_id": run_id,
        "input_payload": input_payload,
        "decision": decision,
        "final_state": final_state,
        "effective_decision": (
            get_latest_effective_decision(
                session_id,
                run_id,
            )
        ),
    }


def requirement_change_response(
    input_payload: Dict[str, Any],
) -> str:
    """Return the established response for changed procurement requirements."""
    return (
        "That changes the procurement scenario and cannot be "
        "answered reliably from the saved recommendation.\n\n"
        "Current scenario:\n"
        f"- Product: {input_payload.get('product_id', 'N/A')}\n"
        f"- Quantity: {input_payload.get('demand_forecast', 'N/A')}\n"
        f"- Required date: {input_payload.get('required_date', 'N/A')}\n\n"
        "Please submit a new Procurement Request with the updated "
        "requirement so the complete workflow can recalculate the result."
    )


def persist_turn(
    session_id: str,
    user_question: str,
    assistant_answer: str,
    analysis: QueryAnalysis,
    trace: ConversationTraceLogger,
) -> None:
    """
    Persist the user and assistant messages, then run the summary check.

    Summarization failure remains non-blocking so a successful answer is not
    lost because of a secondary memory-maintenance failure.
    """
    metadata = {
        "service_version": (
            CONVERSATION_SERVICE_VERSION
        ),
        "query_analysis": (
            analysis.model_dump()
        ),
        "context_scope": (
            analysis.context_scope
        ),
        "trace_log_path": (
            trace.get_log_path()
        ),
    }

    save_message(
        session_id,
        "user",
        user_question,
        metadata={
            "source": "chat_input",
            **metadata,
        },
    )
    save_message(
        session_id,
        "assistant",
        assistant_answer,
        metadata={
            "source": "selective_context_qa",
            **metadata,
        },
    )

    trace.log(
        "persistence",
        "conversation_turn_saved",
        {
            "context_scope": (
                analysis.context_scope
            )
        },
    )

    logger.info(
        "conversation_turn_persisted",
        component="conversation_service",
        status="success",
        payload={
            "context_scope": (
                analysis.context_scope
            ),
            "question_length": (
                len(user_question)
            ),
            "answer_length": (
                len(assistant_answer)
            ),
        },
    )

    try:
        should_summarize = (
            should_summarize_conversation(
                session_id
            )
        )

        trace.log(
            "summarization",
            "summarization_check",
            {
                "should_summarize": (
                    should_summarize
                )
            },
        )

        if should_summarize:
            summary = summarize_conversation(
                session_id
            )
            trace.log(
                "summarization",
                "summary_created",
                {
                    "summary": summary
                },
            )

    except Exception as exc:
        trace.error(
            "summarization",
            "summarization_failed",
            exc,
        )
        logger.exception(
            "conversation_post_turn_summarization_failed",
            error=exc,
            component="conversation_service",
            status="completed_with_warning",
            payload={
                "session_id": session_id,
            },
        )


def _no_context_analysis(
    answer: str,
) -> QueryAnalysis:
    return QueryAnalysis(
        is_in_scope=True,
        intent="unknown_entity",
        can_answer_now=False,
        needs_clarification=False,
        requires_new_procurement_request=False,
        context_scope="none",
        direct_response=answer,
        analysis_reason=(
            "No workflow context exists."
        ),
    )


def _route_answer(
    *,
    analysis: QueryAnalysis,
    user_question: str,
    workflow_context: Dict[str, Any],
    conversation_memory: Dict[str, Any],
    trace: ConversationTraceLogger,
) -> str:
    """Route the analyzed question to a direct or generated response."""
    if (
        not analysis.is_in_scope
        or analysis.intent == "out_of_scope"
    ):
        return (
            "I can only answer questions about this saved "
            "procurement analysis, suppliers, strategies, "
            "review decisions, or PR/PO workflow."
        )

    if (
        analysis.requires_new_procurement_request
    ):
        return requirement_change_response(
            workflow_context["input_payload"]
        )

    if analysis.needs_clarification:
        return (
            analysis.clarification_question
            or (
                "Which item or supplier are you "
                "referring to?"
            )
        )

    if (
        analysis.intent == "unknown_entity"
        and analysis.direct_response
    ):
        return analysis.direct_response

    if not analysis.can_answer_now:
        return (
            "I need more detail about the item or "
            "supplier to answer that."
        )

    selective_context = (
        build_context_from_analysis(
            analysis=analysis,
            input_payload=(
                workflow_context["input_payload"]
            ),
            decision=workflow_context["decision"],
            final_state=(
                workflow_context["final_state"]
            ),
            effective_decision=(
                workflow_context[
                    "effective_decision"
                ]
            ),
        )
    )

    trace.log(
        "context_builder",
        "selective_context_built",
        {
            "context_scope": (
                analysis.context_scope
            ),
            "selective_context": (
                selective_context
            ),
        },
    )

    answer = generate_context_answer(
        question=user_question,
        analysis=analysis,
        selective_context=selective_context,
        conversation_memory=conversation_memory,
    )

    trace.log(
        "answer_generator",
        "answer_generated",
        {"answer": answer},
    )

    return answer


@traceable_if_enabled(
    name="Conversation Workflow",
    run_type="chain",
    tags=[
        "conversation",
        "procurement",
        "follow-up",
    ],
)
def _handle_followup_message_traced(
    session_id: str,
    user_question: str,
    *,
    langsmith_extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Process one procurement follow-up question from analysis to persistence.

    This signature is consumed directly by the Streamlit chat UI.
    """
    if not session_id:
        raise ConversationServiceError(
            "Session ID is required."
        )

    if not user_question.strip():
        raise ConversationServiceError(
            "A follow-up question is required."
        )

    started_at = time.perf_counter()
    workflow_context = (
        load_workflow_context(session_id)
    )
    run_id = workflow_context.get(
        "run_id"
    )
    context_token = bind_log_context(
        session_id=session_id,
        run_id=run_id,
        component="conversation_service",
        conversation_service_version=(
            CONVERSATION_SERVICE_VERSION
        ),
    )
    trace = ConversationTraceLogger(
        session_id,
        run_id,
    )

    logger.info(
        "conversation_followup_started",
        component="conversation_service",
        status="running",
        payload={
            "question_length": (
                len(user_question)
            ),
            "has_workflow_context": bool(
                workflow_context.get(
                    "has_context"
                )
            ),
        },
    )

    trace.log(
        "request",
        "user_question_received",
        {"question": user_question},
    )

    try:
        if not workflow_context.get(
            "has_context"
        ):
            answer = (
                "I do not see a saved procurement "
                "workflow result for this session yet."
            )
            fallback = _no_context_analysis(
                answer
            )
            persist_turn(
                session_id,
                user_question,
                answer,
                fallback,
                trace,
            )
            return answer

        conversation_memory = (
            load_conversation_memory(
                session_id
            )
        )

        entity_index, entity_index_source = (
            get_or_build_entity_index(
                run_id=workflow_context["run_id"],
                final_state=(
                    workflow_context[
                        "final_state"
                    ]
                ),
                decision=(
                    workflow_context["decision"]
                ),
                effective_decision=(
                    workflow_context[
                        "effective_decision"
                    ]
                ),
            )
        )

        trace.log(
            "entity_index",
            "entity_index_ready",
            {
                "source": entity_index_source,
                "entity_index": entity_index,
            },
        )

        logger.info(
            "conversation_entity_index_ready",
            component="conversation_service",
            status="success",
            payload={
                "source": entity_index_source,
                "item_count": len(
                    entity_index.get(
                        "items",
                        [],
                    )
                ),
                "supplier_count": len(
                    entity_index.get(
                        "supplier_to_items",
                        {},
                    )
                ),
            },
        )

        analysis = analyze_user_question(
            question=user_question,
            entity_index=entity_index,
            conversation_memory=(
                conversation_memory
            ),
        )

        trace.log(
            "query_analyzer",
            "analyzer_output",
            {
                "analysis": (
                    analysis.model_dump()
                )
            },
        )

        answer = _route_answer(
            analysis=analysis,
            user_question=user_question,
            workflow_context=(
                workflow_context
            ),
            conversation_memory=(
                conversation_memory
            ),
            trace=trace,
        )

        persist_turn(
            session_id,
            user_question,
            answer,
            analysis,
            trace,
        )

        logger.info(
            "conversation_followup_completed",
            component="conversation_service",
            status="success",
            duration_ms=(
                time.perf_counter()
                - started_at
            )
            * 1000,
            payload={
                "intent": analysis.intent,
                "context_scope": (
                    analysis.context_scope
                ),
                "answer_length": len(answer),
            },
        )

        return answer

    except Exception as exc:
        logger.exception(
            "conversation_followup_failed",
            error=exc,
            component="conversation_service",
            status="failed",
            duration_ms=(
                time.perf_counter()
                - started_at
            )
            * 1000,
            payload={
                "question_length": (
                    len(user_question)
                ),
            },
        )
        raise

    finally:
        reset_log_context(context_token)


def handle_followup_message(
    session_id: str,
    user_question: str,
) -> str:
    """Process one follow-up under a single Conversation Workflow trace."""
    workflow_context = load_workflow_context(session_id)
    input_payload = workflow_context.get("input_payload") or {}
    trace_extra = build_langsmith_extra(
        metadata=build_trace_metadata(
            session_id=session_id,
            run_id=workflow_context.get("run_id"),
            product_id=input_payload.get("product_id"),
            component="conversation_service",
            conversation_service_version=CONVERSATION_SERVICE_VERSION,
        ),
        tags=["conversation", "procurement", "workflow"],
        run_name="Conversation Workflow",
    )
    return _handle_followup_message_traced(
        session_id=session_id,
        user_question=user_question,
        langsmith_extra=trace_extra,
    )
