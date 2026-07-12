"""
LLM-assisted query analysis and deterministic routing normalization.

The analyzer resolves procurement entities, identifies the user intent, applies
guardrails, and selects the minimum context scope required for answer
generation. It does not answer the procurement question.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional, Set

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from conversation.models import QueryAnalysis
from core.config import settings
from core.logging import get_logger
from core.observability import traceable_if_enabled


DEFAULT_ANALYZER_MODEL = settings.conversation_llm_model

RETRIEVAL_INTENTS = {
    "supplier_selection_explanation",
    "supplier_recommendation_explanation",
    "supplier_comparison",
    "supplier_metrics",
    "all_suppliers_for_item",
    "item_explanation",
    "strategy_comparison",
    "effective_plan",
    "human_override",
    "inventory_explanation",
    "pr_po_process",
}

REQUIREMENT_CHANGE_PATTERNS = [
    r"\bwhat if\b.*\b(quantity|demand|required date|deadline|product)\b",
    r"\b(increase|decrease|change|update|modify)\b.*\b(quantity|demand|required date|deadline|product)\b",
    r"\bquantity\b.*\b(to|from)\b",
    r"\bdemand\b.*\b(to|from)\b",
    r"\brequired date\b.*\b(to|from)\b",
    r"\bdeadline\b.*\b(to|from)\b",
    r"\bproduct\b.*\b(to|from)\b",
    r"\bnew quantity\b",
    r"\bnew required date\b",
    r"\bnew deadline\b",
    r"\bnew product\b",
]

BULK_DISCOUNT_TERMS = {
    "bulk discount",
    "volume discount",
    "discount threshold",
    "volume threshold",
    "discount percentage",
    "effective price",
    "effective unit price",
    "discount applied",
}

ALL_SUPPLIERS_TERMS = {
    "all suppliers",
    "every supplier",
    "each supplier",
    "all alternatives",
    "every alternative",
    "each alternative",
}

logger = get_logger("conversation.query_analyzer")


class QueryAnalysisError(RuntimeError):
    """Raised when the LLM query-analysis stage cannot produce a result."""


def _safe_json(
    value: Any,
    max_chars: int = 12000,
) -> str:
    text = json.dumps(
        value,
        indent=2,
        default=str,
    )

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n...TRUNCATED..."


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def question_explicitly_changes_requirement(
    question: str,
) -> bool:
    normalized_question = question.strip().lower()

    return any(
        re.search(
            pattern,
            normalized_question,
        )
        for pattern in REQUIREMENT_CHANGE_PATTERNS
    )


def _known_supplier_names(
    entity_index: Dict[str, Any],
) -> Set[str]:
    names: Set[str] = set()

    for item in entity_index.get("items", []):
        for supplier in (
            item.get("evaluated_suppliers", []) or []
        ):
            names.add(supplier)

    return names


def _find_item_record(
    entity_index: Dict[str, Any],
    item_id: str,
) -> Optional[Dict[str, Any]]:
    for item in entity_index.get("items", []):
        if item.get("item_id") == item_id:
            return item

    return None


def _unknown_supplier_direct_response(
    entity_index: Dict[str, Any],
    item_id: Optional[str],
    unknown_supplier: str,
) -> str:
    if item_id:
        item = _find_item_record(
            entity_index,
            item_id,
        )
        evaluated = (
            (item or {}).get(
                "evaluated_suppliers",
                [],
            )
            or []
        )
        evaluated_text = (
            ", ".join(evaluated)
            if evaluated
            else "No evaluated suppliers were found."
        )

        return (
            f"{unknown_supplier} was not among the suppliers "
            f"evaluated for {item_id}. The evaluated suppliers "
            f"were: {evaluated_text}"
        )

    return (
        f"{unknown_supplier} was not found among the suppliers "
        "evaluated in this procurement session."
    )


def _extract_unknown_named_supplier(
    entity_index: Dict[str, Any],
    analysis: QueryAnalysis,
) -> Optional[str]:
    known_suppliers = {
        _normalize(name)
        for name in _known_supplier_names(
            entity_index
        )
    }

    for supplier_name in analysis.supplier_names:
        if (
            _normalize(supplier_name)
            not in known_suppliers
        ):
            return supplier_name

    return None


def normalize_query_analysis(
    analysis: QueryAnalysis,
    question: str,
    entity_index: Dict[str, Any],
) -> QueryAnalysis:
    """
    Apply deterministic safeguards after LLM classification.

    These rules intentionally preserve the established routing behavior and
    protect against incorrect requirement-change or unknown-entity decisions.
    """
    normalized_question = (
        question.strip().lower()
    )
    explicit_requirement_change = (
        question_explicitly_changes_requirement(
            question
        )
    )

    if not explicit_requirement_change:
        analysis.requires_new_procurement_request = (
            False
        )

    unknown_supplier = (
        _extract_unknown_named_supplier(
            entity_index,
            analysis,
        )
    )

    if unknown_supplier:
        item_id = (
            analysis.item_ids[0]
            if analysis.item_ids
            else None
        )
        analysis.intent = "unknown_entity"
        analysis.can_answer_now = False
        analysis.needs_clarification = False
        analysis.requires_new_procurement_request = (
            False
        )
        analysis.context_scope = "none"
        analysis.direct_response = (
            _unknown_supplier_direct_response(
                entity_index,
                item_id,
                unknown_supplier,
            )
        )
        return analysis

    if (
        any(
            term in normalized_question
            for term in ALL_SUPPLIERS_TERMS
        )
        and analysis.item_ids
    ):
        analysis.intent = (
            "all_suppliers_for_item"
        )
        analysis.context_scope = (
            "all_suppliers_for_item"
        )
        analysis.can_answer_now = True
        analysis.needs_clarification = False
        analysis.direct_response = None

    if any(
        term in normalized_question
        for term in BULK_DISCOUNT_TERMS
    ):
        analysis.intent = "supplier_metrics"

        if (
            analysis.item_ids
            and analysis.supplier_names
        ):
            analysis.context_scope = (
                "supplier_metrics_for_item"
            )
            analysis.can_answer_now = True
            analysis.needs_clarification = False
            analysis.direct_response = None

    if analysis.intent == "human_override":
        analysis.context_scope = "effective_plan"
        analysis.can_answer_now = True
        analysis.needs_clarification = False
        analysis.direct_response = None

    if (
        analysis.intent
        in {
            "supplier_selection_explanation",
            "supplier_recommendation_explanation",
            "supplier_comparison",
        }
        and analysis.item_ids
        and analysis.supplier_names
    ):
        analysis.context_scope = (
            "specific_suppliers_for_item"
            if len(analysis.supplier_names) > 1
            else "specific_supplier_for_item"
        )

    if (
        analysis.is_in_scope
        and analysis.intent in RETRIEVAL_INTENTS
        and not analysis.needs_clarification
        and not (
            analysis.requires_new_procurement_request
        )
        and analysis.context_scope != "none"
    ):
        analysis.can_answer_now = True
        analysis.direct_response = None

    if analysis.needs_clarification:
        analysis.can_answer_now = False
        analysis.direct_response = None

    return analysis


def _build_analyzer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        (
            "system",
            """
You are a routing and guardrail analyzer for a procurement decision assistant.
Do NOT answer the procurement question. Return only QueryAnalysis.

Rules:
- requires_new_procurement_request=true ONLY for an explicit change to product,
  quantity/demand, or required date/deadline.
- Why/how/compare/show-details/discount/override questions are explanations.
- Resolve entities only from the supplied entity index.
- If a supplier belongs to one item, infer the item when safe.
- If it belongs to multiple items and the recent context is not clear, ask for
  clarification.
- For all/every/each supplier requests use all_suppliers_for_item.
- For discount/threshold/effective-price requests use supplier_metrics and
  supplier_metrics_for_item.
- For review/override requests use human_override and effective_plan.
- If a named supplier is not in the index, use unknown_entity.
- Never speculate about unknown suppliers.
""",
        ),
        (
            "human",
            """
User question:
{question}

Compact procurement entity index:
{entity_index}

Conversation summary and recent messages:
{conversation_memory}
""",
        ),
    ])


@traceable_if_enabled(
    name="Conversation Query Analysis",
    run_type="chain",
    tags=[
        "conversation",
        "query-analysis",
        "procurement",
    ],
)
def analyze_user_question(
    question: str,
    entity_index: Dict[str, Any],
    conversation_memory: Dict[str, Any],
    model: str = DEFAULT_ANALYZER_MODEL,
) -> QueryAnalysis:
    """
    Classify one follow-up question and select its retrieval scope.

    The public signature and returned QueryAnalysis schema are preserved for
    the conversation service.
    """
    if not question.strip():
        return QueryAnalysis(
            is_in_scope=False,
            intent="out_of_scope",
            can_answer_now=False,
            needs_clarification=False,
            requires_new_procurement_request=False,
            context_scope="none",
            clarification_question=None,
            direct_response=(
                "Please enter a procurement-related "
                "follow-up question."
            ),
            analysis_reason="The question is empty.",
        )

    started_at = time.perf_counter()

    logger.info(
        "query_analysis_started",
        component="conversation_query_analyzer",
        status="running",
        payload={
            "question_length": len(question),
            "entity_item_count": len(
                entity_index.get("items", [])
            ),
            "model": model,
        },
    )

    try:
        llm = ChatOpenAI(
            model=model,
            temperature=0.0,
        )
        structured_llm = (
            llm.with_structured_output(
                QueryAnalysis
            )
        )
        chain = (
            _build_analyzer_prompt()
            | structured_llm
        )

        analysis = chain.invoke({
            "question": question,
            "entity_index": _safe_json(
                entity_index
            ),
            "conversation_memory": _safe_json(
                conversation_memory,
                max_chars=7000,
            ),
        })

        normalized = normalize_query_analysis(
            analysis=analysis,
            question=question,
            entity_index=entity_index,
        )

    except Exception as exc:
        logger.exception(
            "query_analysis_failed",
            error=exc,
            component="conversation_query_analyzer",
            status="failed",
            duration_ms=(
                time.perf_counter()
                - started_at
            )
            * 1000,
            payload={
                "question_length": len(question),
                "model": model,
            },
        )
        raise QueryAnalysisError(
            "The procurement follow-up question "
            "could not be analyzed."
        ) from exc

    logger.info(
        "query_analysis_completed",
        component="conversation_query_analyzer",
        status="success",
        duration_ms=(
            time.perf_counter()
            - started_at
        )
        * 1000,
        payload={
            "intent": normalized.intent,
            "context_scope": (
                normalized.context_scope
            ),
            "is_in_scope": (
                normalized.is_in_scope
            ),
            "can_answer_now": (
                normalized.can_answer_now
            ),
            "needs_clarification": (
                normalized.needs_clarification
            ),
            "requires_new_procurement_request": (
                normalized.requires_new_procurement_request
            ),
            "item_ids": normalized.item_ids,
            "supplier_names": (
                normalized.supplier_names
            ),
            "strategy_names": (
                normalized.strategy_names
            ),
            "model": model,
        },
    )

    return normalized
