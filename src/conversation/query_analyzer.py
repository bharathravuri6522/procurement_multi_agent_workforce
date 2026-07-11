from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Set

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from conversation.models import QueryAnalysis

DEFAULT_ANALYZER_MODEL = "gpt-4o-mini"

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
    "bulk discount", "volume discount", "discount threshold", "volume threshold",
    "discount percentage", "effective price", "effective unit price", "discount applied",
}

ALL_SUPPLIERS_TERMS = {
    "all suppliers", "every supplier", "each supplier",
    "all alternatives", "every alternative", "each alternative",
}


def _safe_json(value: Any, max_chars: int = 12000) -> str:
    text = json.dumps(value, indent=2, default=str)
    return text if len(text) <= max_chars else text[:max_chars] + "\n...TRUNCATED..."


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def question_explicitly_changes_requirement(question: str) -> bool:
    q = question.strip().lower()
    return any(re.search(pattern, q) for pattern in REQUIREMENT_CHANGE_PATTERNS)


def _known_supplier_names(entity_index: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    for item in entity_index.get("items", []):
        for supplier in item.get("evaluated_suppliers", []) or []:
            names.add(supplier)
    return names


def _find_item_record(entity_index: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    for item in entity_index.get("items", []):
        if item.get("item_id") == item_id:
            return item
    return None


def _unknown_supplier_direct_response(
    entity_index: Dict[str, Any], item_id: Optional[str], unknown_supplier: str
) -> str:
    if item_id:
        item = _find_item_record(entity_index, item_id)
        evaluated = (item or {}).get("evaluated_suppliers", []) or []
        evaluated_text = ", ".join(evaluated) if evaluated else "No evaluated suppliers were found."
        return (
            f"{unknown_supplier} was not among the suppliers evaluated for {item_id}. "
            f"The evaluated suppliers were: {evaluated_text}"
        )
    return f"{unknown_supplier} was not found among the suppliers evaluated in this procurement session."


def _extract_unknown_named_supplier(
    entity_index: Dict[str, Any], analysis: QueryAnalysis
) -> Optional[str]:
    known = {_normalize(name) for name in _known_supplier_names(entity_index)}
    for supplier_name in analysis.supplier_names:
        if _normalize(supplier_name) not in known:
            return supplier_name
    return None


def normalize_query_analysis(
    analysis: QueryAnalysis,
    question: str,
    entity_index: Dict[str, Any],
) -> QueryAnalysis:
    q = question.strip().lower()
    explicit_requirement_change = question_explicitly_changes_requirement(question)

    if not explicit_requirement_change:
        analysis.requires_new_procurement_request = False

    unknown_supplier = _extract_unknown_named_supplier(entity_index, analysis)
    if unknown_supplier:
        item_id = analysis.item_ids[0] if analysis.item_ids else None
        analysis.intent = "unknown_entity"
        analysis.can_answer_now = False
        analysis.needs_clarification = False
        analysis.requires_new_procurement_request = False
        analysis.context_scope = "none"
        analysis.direct_response = _unknown_supplier_direct_response(
            entity_index, item_id, unknown_supplier
        )
        return analysis

    if any(term in q for term in ALL_SUPPLIERS_TERMS) and analysis.item_ids:
        analysis.intent = "all_suppliers_for_item"
        analysis.context_scope = "all_suppliers_for_item"
        analysis.can_answer_now = True
        analysis.needs_clarification = False
        analysis.direct_response = None

    if any(term in q for term in BULK_DISCOUNT_TERMS):
        analysis.intent = "supplier_metrics"
        if analysis.item_ids and analysis.supplier_names:
            analysis.context_scope = "supplier_metrics_for_item"
            analysis.can_answer_now = True
            analysis.needs_clarification = False
            analysis.direct_response = None

    if analysis.intent == "human_override":
        analysis.context_scope = "effective_plan"
        analysis.can_answer_now = True
        analysis.needs_clarification = False
        analysis.direct_response = None

    if (
        analysis.intent in {
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
        and not analysis.requires_new_procurement_request
        and analysis.context_scope != "none"
    ):
        analysis.can_answer_now = True
        analysis.direct_response = None

    if analysis.needs_clarification:
        analysis.can_answer_now = False
        analysis.direct_response = None

    return analysis


def analyze_user_question(
    question: str,
    entity_index: Dict[str, Any],
    conversation_memory: Dict[str, Any],
    model: str = DEFAULT_ANALYZER_MODEL,
) -> QueryAnalysis:
    if not question.strip():
        return QueryAnalysis(
            is_in_scope=False,
            intent="out_of_scope",
            can_answer_now=False,
            needs_clarification=False,
            requires_new_procurement_request=False,
            context_scope="none",
            clarification_question=None,
            direct_response="Please enter a procurement-related follow-up question.",
            analysis_reason="The question is empty.",
        )

    prompt = ChatPromptTemplate.from_messages([
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
- If it belongs to multiple items and the recent context is not clear, ask for clarification.
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

    llm = ChatOpenAI(model=model, temperature=0.0)
    chain = prompt | llm.with_structured_output(QueryAnalysis)
    analysis = chain.invoke({
        "question": question,
        "entity_index": _safe_json(entity_index),
        "conversation_memory": _safe_json(conversation_memory, max_chars=7000),
    })
    return normalize_query_analysis(analysis, question, entity_index)
