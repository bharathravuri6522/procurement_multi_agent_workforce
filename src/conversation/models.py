from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

QueryIntent = Literal[
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
    "requirement_change",
    "pr_po_process",
    "unknown_entity",
    "out_of_scope",
]

ContextScope = Literal[
    "specific_supplier_for_item",
    "specific_suppliers_for_item",
    "supplier_metrics_for_item",
    "all_suppliers_for_item",
    "specific_item",
    "strategy_comparison",
    "effective_plan",
    "decision_summary",
    "none",
]


class QueryAnalysis(BaseModel):
    is_in_scope: bool
    intent: QueryIntent
    can_answer_now: bool
    needs_clarification: bool
    requires_new_procurement_request: bool
    context_scope: ContextScope
    item_ids: List[str] = Field(default_factory=list)
    supplier_names: List[str] = Field(default_factory=list)
    strategy_names: List[str] = Field(default_factory=list)
    clarification_question: Optional[str] = None
    direct_response: Optional[str] = None
    analysis_reason: str
