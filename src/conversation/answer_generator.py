"""
Grounded answer generation for procurement follow-up questions.

The generator receives normalized query analysis, conversation memory, and a
selective procurement context. It does not retrieve data or rerun procurement.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from conversation.models import QueryAnalysis
from core.config import settings
from core.logging import get_logger
from core.observability import traceable_if_enabled


DEFAULT_ANSWER_MODEL = settings.conversation_llm_model

logger = get_logger("conversation.answer_generator")


class AnswerGenerationError(RuntimeError):
    """Raised when a grounded conversation answer cannot be generated."""


def _safe_json(
    value: Any,
    max_chars: int = 22000,
) -> str:
    text = json.dumps(
        value,
        indent=2,
        default=str,
    )

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n...TRUNCATED..."


def _build_answer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        (
            "system",
            """
You are a senior procurement decision explanation assistant.
Use only the supplied selective context. Never invent or infer missing
supplier facts.

General rules:
- Match the depth to the user intent; do not repeat the same full report each
  time.
- Existing agent reasoning is concise evidence; expand it only as needed.
- If information is absent, identify the exact missing field.
- Higher overage is not automatically a benefit. Treat it as an excess
  inventory and carrying-cost trade-off unless the context explicitly says
  extra buffer is desired.

Intent behavior:
- supplier_selection_explanation: focus on why the requested alternative was
  rejected versus the selected supplier.
- supplier_recommendation_explanation: focus on why the selected supplier was
  chosen; mention alternatives briefly.
- supplier_comparison: focus on the named suppliers; use the selected supplier
  only as a baseline when relevant.
- all_suppliers_for_item: explain every entry in supplier_records and ensure
  the number discussed equals supplier_count.
- supplier_metrics: use supplier order quantity, not product demand. For
  discounts, state threshold, discount percentage, applied flag, before/after
  price, and total cost only when those fields are present. Use plain currency
  formatting.
- human_override: when effective_decision is absent, state exactly:
  "No supplier or strategy override has been recorded for this session."
- unknown entities: never speculate about unevaluated suppliers.

End with a concise conclusion appropriate to the question.
""",
        ),
        (
            "human",
            """
Question:
{question}

Query analysis:
{analysis}

Conversation memory:
{conversation_memory}

Selective procurement context:
{selective_context}
""",
        ),
    ])


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


@traceable_if_enabled(
    name="Conversation Answer Generation",
    run_type="chain",
    tags=[
        "conversation",
        "answer-generation",
        "procurement",
    ],
)
def generate_context_answer(
    question: str,
    analysis: QueryAnalysis,
    selective_context: Dict[str, Any],
    conversation_memory: Dict[str, Any],
    model: str = DEFAULT_ANSWER_MODEL,
) -> str:
    """
    Generate a grounded answer from the supplied selective context.

    The public signature and string return value are preserved for the
    conversation service and Streamlit chat layer.
    """
    if not question.strip():
        raise AnswerGenerationError(
            "A user question is required for answer generation."
        )

    if not isinstance(analysis, QueryAnalysis):
        raise AnswerGenerationError(
            "Query analysis must be a QueryAnalysis instance."
        )

    started_at = time.perf_counter()

    logger.info(
        "answer_generation_started",
        component="conversation_answer_generator",
        status="running",
        payload={
            "intent": analysis.intent,
            "context_scope": analysis.context_scope,
            "question_length": len(question),
            "context_top_level_keys": sorted(
                selective_context.keys()
            ),
            "model": model,
        },
    )

    try:
        llm = ChatOpenAI(
            model=model,
            temperature=0.0,
        )
        chain = _build_answer_prompt() | llm

        response = chain.invoke({
            "question": question,
            "analysis": analysis.model_dump_json(
                indent=2
            ),
            "conversation_memory": _safe_json(
                conversation_memory,
                max_chars=6000,
            ),
            "selective_context": _safe_json(
                selective_context,
                max_chars=22000,
            ),
        })

        answer = _response_text(response)

        if not answer:
            raise AnswerGenerationError(
                "The model returned an empty answer."
            )

    except AnswerGenerationError:
        raise
    except Exception as exc:
        logger.exception(
            "answer_generation_failed",
            error=exc,
            component="conversation_answer_generator",
            status="failed",
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
                "question_length": len(question),
                "model": model,
            },
        )
        raise AnswerGenerationError(
            "The procurement follow-up answer "
            "could not be generated."
        ) from exc

    logger.info(
        "answer_generation_completed",
        component="conversation_answer_generator",
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
            "model": model,
        },
    )

    return answer
