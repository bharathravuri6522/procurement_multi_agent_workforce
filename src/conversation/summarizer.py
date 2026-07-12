"""
Conversation summarization for long-running procurement follow-up sessions.

The summarizer condenses persisted messages into reusable context while
preserving procurement requirements, recommendations, overrides, effective
plans, unresolved questions, and PR/PO status.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from core.logging import get_logger
from core.observability import traceable_if_enabled
from persistence import (
    load_latest_conversation_summary,
    load_messages,
    save_conversation_summary,
)


DEFAULT_SUMMARY_MODEL = settings.conversation_llm_model
SUMMARY_TRIGGER_MESSAGE_COUNT = 8
SUMMARY_MESSAGE_LIMIT = 100
SUMMARIZER_VERSION = "conversation_summarizer_v2 | coverage-aware"

logger = get_logger("conversation.summarizer")


class ConversationSummarizationError(RuntimeError):
    """Raised when a conversation summary cannot be generated or saved."""


def _safe_json(
    value: Any,
    max_chars: int = 16000,
) -> str:
    text = json.dumps(
        value,
        indent=2,
        default=str,
    )

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n...TRUNCATED..."


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")

                if text:
                    parts.append(str(text))

        if parts:
            return "\n".join(parts).strip()

    return str(content).strip()


def _messages_covered(
    summary_record: Optional[dict],
) -> int:
    if not summary_record:
        return 0

    value = summary_record.get(
        "messages_covered",
        0,
    )

    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def should_summarize_conversation(
    session_id: str,
    trigger_message_count: int = (
        SUMMARY_TRIGGER_MESSAGE_COUNT
    ),
) -> bool:
    """
    Return true when enough new messages exist beyond the latest summary.

    The original eight-message threshold is preserved, but the decision now
    uses persisted summary coverage rather than a total-count modulo check.
    """
    if not session_id:
        return False

    if trigger_message_count <= 0:
        raise ValueError(
            "Summary trigger message count must be greater than zero."
        )

    messages = load_messages(
        session_id,
        limit=SUMMARY_MESSAGE_LIMIT,
    )
    message_count = len(messages)

    if message_count < trigger_message_count:
        return False

    latest_summary = (
        load_latest_conversation_summary(
            session_id
        )
    )
    covered_count = _messages_covered(
        latest_summary
    )
    new_message_count = max(
        0,
        message_count - covered_count,
    )

    should_summarize = (
        new_message_count
        >= trigger_message_count
    )

    logger.info(
        "conversation_summarization_check",
        component="conversation_summarizer",
        status="success",
        payload={
            "session_id": session_id,
            "message_count": message_count,
            "messages_covered": covered_count,
            "new_message_count": new_message_count,
            "trigger_message_count": (
                trigger_message_count
            ),
            "should_summarize": (
                should_summarize
            ),
        },
    )

    return should_summarize


def _build_summary_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        (
            "system",
            """
Summarize this procurement conversation for future follow-up context.

Preserve:
- product, quantity, and required date;
- recommended strategy and suppliers;
- important supplier explanations and comparisons;
- human overrides and the effective plan;
- unresolved questions or requested clarifications;
- Purchase Requisition and Purchase Order status.

Exclude unrelated content. Do not invent information. Produce a concise,
fact-focused summary that supports future procurement follow-up questions.
""",
        ),
        (
            "human",
            """
Existing summary:
{existing_summary}

Persisted conversation messages:
{messages}
""",
        ),
    ])


@traceable_if_enabled(
    name="Conversation Summarization",
    run_type="chain",
    tags=[
        "conversation",
        "summarization",
        "procurement",
    ],
)
def summarize_conversation(
    session_id: str,
    model: str = DEFAULT_SUMMARY_MODEL,
) -> Optional[str]:
    """
    Generate and persist the latest procurement conversation summary.

    The public signature and optional string return value are preserved for
    the conversation service.
    """
    if not session_id:
        raise ConversationSummarizationError(
            "Session ID is required for conversation summarization."
        )

    messages = load_messages(
        session_id,
        limit=SUMMARY_MESSAGE_LIMIT,
    )

    if not messages:
        return None

    latest_summary = (
        load_latest_conversation_summary(
            session_id
        )
    )
    existing_summary = (
        latest_summary.get("summary_text")
        if latest_summary
        else None
    )

    started_at = time.perf_counter()

    logger.info(
        "conversation_summarization_started",
        component="conversation_summarizer",
        status="running",
        payload={
            "session_id": session_id,
            "message_count": len(messages),
            "has_existing_summary": bool(
                existing_summary
            ),
            "model": model,
        },
    )

    try:
        llm = ChatOpenAI(
            model=model,
            temperature=0.0,
        )
        chain = _build_summary_prompt() | llm

        response = chain.invoke({
            "existing_summary": (
                existing_summary
                or "No existing summary."
            ),
            "messages": _safe_json(messages),
        })

        summary = _response_text(response)

        if not summary:
            raise ConversationSummarizationError(
                "The model returned an empty conversation summary."
            )

        save_conversation_summary(
            session_id=session_id,
            summary_text=summary,
            messages_covered=len(messages),
            metadata={
                "version": SUMMARIZER_VERSION,
                "message_count": len(messages),
                "model": model,
            },
        )

    except ConversationSummarizationError:
        raise
    except Exception as exc:
        logger.exception(
            "conversation_summarization_failed",
            error=exc,
            component="conversation_summarizer",
            status="failed",
            duration_ms=(
                time.perf_counter()
                - started_at
            )
            * 1000,
            payload={
                "session_id": session_id,
                "message_count": len(messages),
                "model": model,
            },
        )
        raise ConversationSummarizationError(
            "The procurement conversation could not be summarized."
        ) from exc

    logger.info(
        "conversation_summarization_completed",
        component="conversation_summarizer",
        status="success",
        duration_ms=(
            time.perf_counter()
            - started_at
        )
        * 1000,
        payload={
            "session_id": session_id,
            "message_count": len(messages),
            "summary_length": len(summary),
            "model": model,
        },
    )

    return summary
