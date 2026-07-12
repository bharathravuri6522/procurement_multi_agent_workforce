"""
Structured models shared across the conversational procurement workflow.

These models define the query-analysis contract used by the analyzer,
context builder, answer generator, service layer, and persisted metadata.
"""

from __future__ import annotations

from typing import List, Literal, Optional, TypeAlias

from pydantic import BaseModel, Field


QueryIntent: TypeAlias = Literal[
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


ContextScope: TypeAlias = Literal[
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
    """
    Structured classification and routing result for one user question.

    The schema is intentionally stable because downstream conversation
    components and persisted message metadata depend on these field names.
    """

    is_in_scope: bool = Field(
        description=(
            "Whether the question belongs to the saved procurement "
            "analysis or its PR/PO lifecycle."
        )
    )
    intent: QueryIntent = Field(
        description=(
            "Normalized conversation intent used for routing and "
            "selective context retrieval."
        )
    )
    can_answer_now: bool = Field(
        description=(
            "Whether the saved procurement context is sufficient to "
            "answer without requesting clarification or rerunning the "
            "procurement workflow."
        )
    )
    needs_clarification: bool = Field(
        description=(
            "Whether the user must clarify an ambiguous item, supplier, "
            "strategy, or request."
        )
    )
    requires_new_procurement_request: bool = Field(
        description=(
            "Whether the question changes the procurement requirement "
            "and therefore requires a new workflow run."
        )
    )
    context_scope: ContextScope = Field(
        description=(
            "The smallest procurement context scope required for answer "
            "generation."
        )
    )

    item_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Resolved procurement item identifiers referenced by the "
            "question."
        ),
    )
    supplier_names: List[str] = Field(
        default_factory=list,
        description=(
            "Resolved supplier names referenced by the question."
        ),
    )
    strategy_names: List[str] = Field(
        default_factory=list,
        description=(
            "Resolved procurement strategies referenced by the question."
        ),
    )

    clarification_question: Optional[str] = Field(
        default=None,
        description=(
            "A focused follow-up question when the original request is "
            "ambiguous."
        ),
    )
    direct_response: Optional[str] = Field(
        default=None,
        description=(
            "A response that can be returned without building additional "
            "procurement context."
        ),
    )
    analysis_reason: str = Field(
        description=(
            "A concise explanation of the classification and routing "
            "decision for observability and debugging."
        )
    )
