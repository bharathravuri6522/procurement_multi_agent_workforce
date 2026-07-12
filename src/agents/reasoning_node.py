"""
Contracted supplier reasoning with structured LLM output.

The node recommends one supplier per item and builds a product-level summary
covering critical path, feasibility, chosen suppliers, and total cost.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core.exceptions import SupplierReasoningError
from core.logging import get_logger
from core.observability import traceable_if_enabled


REASONING_NODE_VERSION = (
    "reasoning_node_v2 | production-clean-and-comparison-guardrails"
)
REASONING_MODEL = "gpt-4o"

logger = get_logger("contracted_reasoning")


class RecommendedSupplier(BaseModel):
    supplier_id: str
    supplier_name: str
    reasoning: str = Field(
        ...,
        description=(
            "Detailed explanation covering cost, risk, lead-time "
            "feasibility, overage impact, and alignment with the "
            "required date."
        ),
    )
    total_cost: float
    effective_unit_price: float
    risk_level: str
    lead_time_days: int
    overage_quantity: int
    bulk_discount_applied: bool
    can_deliver_on_time: bool


class AlternativeSupplier(BaseModel):
    supplier_name: str
    why_not_selected: str
    total_cost: float
    risk_level: str


class ReasoningOutput(BaseModel):
    item_id: str
    item_name: str
    gross_requirement: float
    required_date: str
    recommended_supplier: RecommendedSupplier
    alternatives_considered: List[AlternativeSupplier]
    key_tradeoffs: List[str]
    overall_assessment: str


class ProductLevelSummary(BaseModel):
    critical_path_days: int
    suggested_realistic_date: str
    is_original_date_feasible: bool
    overall_message: str
    chosen_suppliers_summary: List[dict]
    total_procurement_cost: float


class FullReasoningResult(BaseModel):
    items: List[ReasoningOutput]
    product_level: ProductLevelSummary


def get_available_days(required_date_str: str | None) -> int:
    if not required_date_str:
        return 30

    try:
        required = datetime.strptime(
            required_date_str,
            "%Y-%m-%d",
        ).date()
    except (TypeError, ValueError):
        logger.warning(
            "reasoning_required_date_defaulted",
            component="contracted_reasoning",
            status="completed_with_warning",
            payload={
                "required_date": required_date_str,
                "default_available_days": 30,
            },
        )
        return 30

    return max(0, (required - date.today()).days)


def calculate_suggested_date(
    critical_path_days: int,
    buffer_days: int = 1,
) -> str:
    suggested = date.today() + timedelta(
        days=critical_path_days + buffer_days
    )
    return suggested.strftime("%Y-%m-%d")


def _supplier_context(
    supplier: Dict[str, Any],
    available_days: int,
) -> str:
    lead_time = supplier.get("current_lead_time")

    try:
        lead_time_value = int(float(lead_time))
        timeline_feasible = lead_time_value <= available_days
    except (TypeError, ValueError):
        timeline_feasible = False

    return f"""
Supplier: {supplier.get('supplier_name')} ({supplier.get('supplier_id')})
- Risk Level: {supplier.get('risk_level')}
- Lead Time: {lead_time} days
- Timeline Feasible: {timeline_feasible}
- Available Days: {available_days}
- On-time Delivery: {supplier.get('on_time_delivery_pct')}%
- Quality Rejection: {supplier.get('quality_rejection_pct')}%
- Capacity: {supplier.get('capacity_status')}
- Contracted Price: {supplier.get('contracted_price')}
- Spot Price: {supplier.get('spot_price')}
- MOQ: {supplier.get('moq')}
- Recommended Order Qty (Batch): {supplier.get('recommended_order_quantity')}
- Total Cost (Contracted after discount): {supplier.get('total_cost_contracted')}
- Total Cost (Spot): {supplier.get('total_cost_spot')}
- Effective Unit Price (Contracted): {supplier.get('effective_unit_price_contracted')}
- Overage Quantity: {supplier.get('overage_quantity')}
- Bulk Discount Applied: {supplier.get('bulk_discount_applied')}
"""


def _build_reasoning_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a highly disciplined procurement decision engine.

Recommend exactly one best contracted supplier for the item using this strict
priority order:

1. Timeline feasibility: lead time must be compared with available days.
2. Risk and reliability: prefer lower risk, stronger on-time delivery, and
   lower quality rejection.
3. Total contracted cost after discount.
4. Inventory impact from MOQ overage.

Strict accuracy rules:
- Use only the supplied data.
- Verify every cheaper/more-expensive statement against the supplied
  contracted total-cost values before writing it.
- Never say an alternative is more expensive when its total cost is lower,
  and never say it is cheaper when its total cost is higher.
- A supplier is timeline-feasible when Lead Time <= Available Days.
- Never call a supplier infeasible when Lead Time <= Available Days.
- Use the phrase "only feasible supplier" only when exactly one supplier has
  Timeline Feasible: True.
- When multiple suppliers are feasible, explain why the selected supplier is
  preferred; do not imply the alternatives cannot meet the date.
- If no supplier is feasible, state that clearly and select the shortest-lead
  option with the strongest reliability profile.
- Preserve the decision-priority order. Do not select randomly when options
  are close.
- Return all non-selected suppliers in alternatives_considered.
- Ensure recommended_supplier.can_deliver_on_time matches the supplied
  timeline-feasibility fact.
- Do not invent metrics or reverse numerical comparisons.

Reason internally, then return only the required structured output.""",
        ),
        (
            "human",
            """Item: {item_name} ({item_id})
Gross Requirement: {gross_requirement}
Required Date: {required_date}
Available Days until Required Date: {available_days}

Suppliers Data:
{suppliers_data}

Return the required structured analysis.""",
        ),
    ])


@traceable_if_enabled(
    name="Contracted Supplier Item Reasoning",
    run_type="chain",
    tags=["procurement", "contracted-reasoning", "item"],
)
def _reason_for_item(
    *,
    item_id: str,
    item_name: str,
    gross_requirement: float,
    required_date: str,
    available_days: int,
    suppliers: List[Dict[str, Any]],
) -> ReasoningOutput:
    llm = ChatOpenAI(
        model=REASONING_MODEL,
        temperature=0.0,
    )
    structured_llm = llm.with_structured_output(
        ReasoningOutput
    )
    chain = _build_reasoning_prompt() | structured_llm

    suppliers_data = "\n".join(
        _supplier_context(
            supplier,
            available_days,
        )
        for supplier in suppliers
    )

    return chain.invoke({
        "item_name": item_name,
        "item_id": item_id,
        "gross_requirement": gross_requirement,
        "required_date": required_date,
        "available_days": available_days,
        "suppliers_data": suppliers_data,
    })


def _build_product_summary(
    *,
    item_results: List[ReasoningOutput],
    required_date: str,
    available_days: int,
) -> ProductLevelSummary:
    if not item_results:
        return ProductLevelSummary(
            critical_path_days=0,
            suggested_realistic_date="N/A",
            is_original_date_feasible=False,
            overall_message="No items to analyze.",
            chosen_suppliers_summary=[],
            total_procurement_cost=0.0,
        )

    critical_path = max(
        result.recommended_supplier.lead_time_days
        for result in item_results
    )
    suggested_date = calculate_suggested_date(
        critical_path,
        buffer_days=1,
    )
    is_feasible = critical_path <= available_days

    if is_feasible:
        message = (
            "All items can be procured within the required "
            f"date of {required_date}."
        )
    else:
        message = (
            "The original required date is not feasible. "
            "A realistic fulfillment date would be around "
            f"{suggested_date}."
        )

    chosen_summary = []
    total_cost = 0.0

    for result in item_results:
        recommendation = result.recommended_supplier

        chosen_summary.append({
            "item_id": result.item_id,
            "item_name": result.item_name,
            "supplier_name": recommendation.supplier_name,
            "order_quantity": (
                recommendation.overage_quantity
                + result.gross_requirement
            ),
            "lead_time_days": recommendation.lead_time_days,
            "cost": recommendation.total_cost,
        })
        total_cost += recommendation.total_cost

    return ProductLevelSummary(
        critical_path_days=critical_path,
        suggested_realistic_date=suggested_date,
        is_original_date_feasible=is_feasible,
        overall_message=message,
        chosen_suppliers_summary=chosen_summary,
        total_procurement_cost=round(total_cost, 2),
    )


def reason_and_recommend(
    supplier_intelligence_output: Dict[str, Any],
) -> FullReasoningResult:
    """
    Recommend contracted suppliers and calculate the product critical path.

    The public signature and structured output schema are preserved for the
    supervisor, aggregator, persistence, conversation, and UI layers.
    """
    if not isinstance(supplier_intelligence_output, dict):
        raise SupplierReasoningError(
            "Supplier intelligence output must be a dictionary.",
            component="contracted_reasoning",
        )

    required_date = (
        supplier_intelligence_output.get("required_date")
        or "N/A"
    )
    available_days = get_available_days(
        supplier_intelligence_output.get("required_date")
    )
    items = (
        supplier_intelligence_output.get(
            "items_analyzed",
            [],
        )
        or []
    )

    item_results: List[ReasoningOutput] = []

    for item in items:
        item_id = item.get("item_id")
        item_name = item.get("item_name", "")
        gross_requirement = item.get(
            "gross_requirement",
            0,
        )
        suppliers = item.get("suppliers", []) or []

        if not suppliers:
            logger.warning(
                "contracted_reasoning_item_skipped",
                component="contracted_reasoning",
                status="completed_with_warning",
                payload={
                    "item_id": item_id,
                    "reason": "no_supplier_options",
                },
            )
            continue

        started_at = time.perf_counter()

        logger.info(
            "contracted_item_reasoning_started",
            component="contracted_reasoning",
            status="running",
            payload={
                "item_id": item_id,
                "supplier_count": len(suppliers),
                "model": REASONING_MODEL,
            },
        )

        try:
            response = _reason_for_item(
                item_id=item_id,
                item_name=item_name,
                gross_requirement=gross_requirement,
                required_date=required_date,
                available_days=available_days,
                suppliers=suppliers,
            )
        except Exception as exc:
            logger.exception(
                "contracted_item_reasoning_failed",
                error=exc,
                component="contracted_reasoning",
                status="failed",
                duration_ms=(
                    time.perf_counter() - started_at
                )
                * 1000,
                payload={
                    "item_id": item_id,
                    "supplier_count": len(suppliers),
                    "model": REASONING_MODEL,
                },
            )
            raise SupplierReasoningError(
                f"Contracted supplier reasoning failed for item {item_id}.",
                component="contracted_reasoning",
            ) from exc

        item_results.append(response)

        logger.info(
            "contracted_item_reasoning_completed",
            component="contracted_reasoning",
            status="success",
            duration_ms=(
                time.perf_counter() - started_at
            )
            * 1000,
            payload={
                "item_id": item_id,
                "selected_supplier": (
                    response.recommended_supplier.supplier_name
                ),
                "supplier_count": len(suppliers),
                "model": REASONING_MODEL,
            },
        )

    product_summary = _build_product_summary(
        item_results=item_results,
        required_date=required_date,
        available_days=available_days,
    )

    return FullReasoningResult(
        items=item_results,
        product_level=product_summary,
    )
