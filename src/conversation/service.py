from __future__ import annotations

import json
from typing import Any, Dict, Optional

from persistence import (
    load_latest_workflow_run,
    load_messages,
    load_latest_conversation_summary,
    load_session_activity,
    save_message,
)

from conversation.answer_generator import generate_context_answer
from conversation.context_builder import build_context_from_analysis
from conversation.debug_logger import ConversationTraceLogger
from conversation.entity_index import get_or_build_entity_index
from conversation.models import QueryAnalysis
from conversation.query_analyzer import analyze_user_question
from conversation.summarizer import should_summarize_conversation, summarize_conversation

CONVERSATION_SERVICE_VERSION = "conversation_service_v7 | normalized-routing-deep-supplier-explanation"


def load_conversation_memory(session_id: str, recent_limit: int = 6) -> Dict[str, Any]:
    latest_summary = load_latest_conversation_summary(session_id)
    return {
        "summary": latest_summary.get("summary_text") if latest_summary else None,
        "summary_record": latest_summary,
        "recent_messages": load_messages(session_id, limit=recent_limit),
    }


def get_latest_effective_decision(session_id: str, run_id: Optional[str]) -> Optional[Dict[str, Any]]:
    for activity in load_session_activity(session_id, limit=50):
        if run_id and activity.get("run_id") != run_id:
            continue
        details = activity.get("details") or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                details = {}
        effective = details.get("effective_decision") or details.get("effective_plan") or details.get("metadata", {}).get("effective_plan")
        if effective:
            return effective
    return None


def load_workflow_context(session_id: str) -> Dict[str, Any]:
    latest_run = load_latest_workflow_run(session_id)
    if not latest_run:
        return {"has_context": False}

    final_state = latest_run.get("final_state") or latest_run.get("final_state_json") or {}
    decision = latest_run.get("decision_aggregation") or latest_run.get("decision_aggregation_json") or {}
    input_payload = latest_run.get("input_payload") or latest_run.get("input_payload_json") or {}
    run_id = latest_run.get("run_id")

    return {
        "has_context": True,
        "run_id": run_id,
        "input_payload": input_payload,
        "decision": decision,
        "final_state": final_state,
        "effective_decision": get_latest_effective_decision(session_id, run_id),
    }


def requirement_change_response(input_payload: Dict[str, Any]) -> str:
    return (
        "That changes the procurement scenario and cannot be answered reliably from the saved recommendation.\n\n"
        f"Current scenario:\n- Product: {input_payload.get('product_id', 'N/A')}\n"
        f"- Quantity: {input_payload.get('demand_forecast', 'N/A')}\n"
        f"- Required date: {input_payload.get('required_date', 'N/A')}\n\n"
        "Please submit a new Procurement Request with the updated requirement so the complete workflow can recalculate the result."
    )


def persist_turn(
    session_id: str,
    user_question: str,
    assistant_answer: str,
    analysis: QueryAnalysis,
    trace: ConversationTraceLogger,
) -> None:
    metadata = {
        "service_version": CONVERSATION_SERVICE_VERSION,
        "query_analysis": analysis.model_dump(),
        "context_scope": analysis.context_scope,
        "trace_log_path": trace.get_log_path(),
    }
    save_message(session_id, "user", user_question, metadata={"source": "chat_input", **metadata})
    save_message(session_id, "assistant", assistant_answer, metadata={"source": "selective_context_qa", **metadata})
    trace.log("persistence", "conversation_turn_saved", {"context_scope": analysis.context_scope})

    try:
        should_summarize = should_summarize_conversation(session_id)
        trace.log("summarization", "summarization_check", {"should_summarize": should_summarize})
        if should_summarize:
            summary = summarize_conversation(session_id)
            trace.log("summarization", "summary_created", {"summary": summary})
    except Exception as exc:
        trace.error("summarization", "summarization_failed", exc)


def handle_followup_message(session_id: str, user_question: str) -> str:
    workflow_context = load_workflow_context(session_id)
    run_id = workflow_context.get("run_id") if workflow_context else None
    trace = ConversationTraceLogger(session_id, run_id)
    trace.log("request", "user_question_received", {"question": user_question})

    if not workflow_context.get("has_context"):
        answer = "I do not see a saved procurement workflow result for this session yet."
        fallback = QueryAnalysis(
            is_in_scope=True,
            intent="unknown_entity",
            can_answer_now=False,
            needs_clarification=False,
            requires_new_procurement_request=False,
            context_scope="none",
            direct_response=answer,
            analysis_reason="No workflow context exists.",
        )
        persist_turn(session_id, user_question, answer, fallback, trace)
        return answer

    conversation_memory = load_conversation_memory(session_id)
    entity_index, entity_index_source = get_or_build_entity_index(
        run_id=workflow_context["run_id"],
        final_state=workflow_context["final_state"],
        decision=workflow_context["decision"],
        effective_decision=workflow_context["effective_decision"],
    )
    trace.log("entity_index", "entity_index_ready", {"source": entity_index_source, "entity_index": entity_index})

    analysis = analyze_user_question(
        question=user_question,
        entity_index=entity_index,
        conversation_memory=conversation_memory,
    )
    trace.log("query_analyzer", "analyzer_output", {"analysis": analysis.model_dump()})

    if not analysis.is_in_scope or analysis.intent == "out_of_scope":
        answer = "I can only answer questions about this saved procurement analysis, suppliers, strategies, review decisions, or PR/PO workflow."
    elif analysis.requires_new_procurement_request:
        answer = requirement_change_response(workflow_context["input_payload"])
    elif analysis.needs_clarification:
        answer = analysis.clarification_question or "Which item or supplier are you referring to?"
    elif analysis.intent == "unknown_entity" and analysis.direct_response:
        answer = analysis.direct_response
    elif analysis.can_answer_now:
        selective_context = build_context_from_analysis(
            analysis=analysis,
            input_payload=workflow_context["input_payload"],
            decision=workflow_context["decision"],
            final_state=workflow_context["final_state"],
            effective_decision=workflow_context["effective_decision"],
        )
        trace.log("context_builder", "selective_context_built", {"context_scope": analysis.context_scope, "selective_context": selective_context})
        answer = generate_context_answer(
            question=user_question,
            analysis=analysis,
            selective_context=selective_context,
            conversation_memory=conversation_memory,
        )
        trace.log("answer_generator", "answer_generated", {"answer": answer})
    else:
        answer = "I need more detail about the item or supplier to answer that."

    persist_turn(session_id, user_question, answer, analysis, trace)
    return answer
