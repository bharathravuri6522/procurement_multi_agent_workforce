"""
Spot procurement reasoning with structured LLM output.

Spot feasibility uses the item-level standard lead time for every supplier of
the same item. Supplier-specific contracted lead time remains reference data
only and is never used as the spot lead time.
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


SPOT_REASONING_VERSION = (
    "spot_reasoning_node_v3 | production-clean-item-lead-time"
)
SPOT_REASONING_MODEL = "gpt-4o"
SPOT_BUFFER_DAYS = 1

logger = get_logger("spot_reasoning")


class SpotRecommendedSupplier(BaseModel):
    supplier_id: str
    supplier_name: str
    reasoning: str = Field(
        ...,
        description=(
            "Why this supplier was chosen for spot procurement."
        ),
    )

    # Generic fields retained for existing logger and UI compatibility.
    total_cost: float
    effective_unit_price: float
    lead_time_days: int
    bulk_discount_applied: bool = False

    # Spot-specific fields.
    total_spot_cost: float
    spot_unit_price: float
    cost_delta_vs_contracted: float
    cost_delta_pct_vs_contracted: float
    risk_level: str
    item_standard_lead_time_days: int
    original_contract_lead_time_days: int
    overage_quantity: int
    can_deliver_on_time: bool
    spot_strategy_value: str


class SpotAlternativeSupplier(BaseModel):
    supplier_name: str
    why_not_selected: str
    total_spot_cost: float
    item_standard_lead_time_days: int
    risk_level: str


class SpotReasoningOutput(BaseModel):
    item_id: str
    item_name: str
    gross_requirement: float
    required_date: str
    recommended_supplier: SpotRecommendedSupplier
    alternatives_considered: List[SpotAlternativeSupplier]
    key_tradeoffs: List[str]
    overall_assessment: str


class SpotProductLevelSummary(BaseModel):
    critical_path_days: int
    suggested_realistic_date: str
    is_original_date_feasible: bool
    overall_message: str
    chosen_suppliers_summary: List[dict]
    total_procurement_cost: float
    total_spot_procurement_cost: float
    spot_strategy_assessment: str


class FullSpotReasoningResult(BaseModel):
    items: List[SpotReasoningOutput]
    product_level: SpotProductLevelSummary


def _get_available_days(
    required_date_str: str | None,
) -> int:
    if not required_date_str:
        return 30

    try:
        required = datetime.strptime(
            required_date_str,
            "%Y-%m-%d",
        ).date()
    except (TypeError, ValueError):
        logger.warning(
            "spot_required_date_defaulted",
            component="spot_reasoning",
            status="completed_with_warning",
            payload={
                "required_date": required_date_str,
                "default_available_days": 30,
            },
        )
        return 30

    return max(0, (required - date.today()).days)


def _calculate_suggested_date(
    critical_path_days: int,
    buffer_days: int = SPOT_BUFFER_DAYS,
) -> str:
    return (
        date.today()
        + timedelta(
            days=critical_path_days + buffer_days
        )
    ).strftime("%Y-%m-%d")


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value in (None, "", "Not available"):
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value in (None, "", "Not available"):
            return default

        return int(float(value))
    except (TypeError, ValueError):
        return default


def _get_item_standard_lead_time(
    item: Dict[str, Any],
) -> int:
    value = item.get(
        "item_standard_lead_time_days"
    )

    if value not in (
        None,
        "",
        "Not available",
    ):
        return _safe_int(
            value,
            default=30,
        )

    inventory_status = (
        item.get("inventory_status") or {}
    )

    return _safe_int(
        inventory_status.get("lead_time_days"),
        default=30,
    )


def enrich_suppliers_for_spot_strategy(
    item: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Add spot-specific fields while using one item-level lead time.

    This function intentionally preserves supplier-specific contract lead time
    only as comparison data.
    """
    item_standard_lead_time = (
        _get_item_standard_lead_time(item)
    )
    enriched_suppliers: List[Dict[str, Any]] = []

    for supplier in item.get("suppliers", []) or []:
        enriched_supplier = dict(supplier)

        contracted_total = _safe_float(
            enriched_supplier.get(
                "total_cost_contracted"
            ),
            0.0,
        )
        spot_total = _safe_float(
            enriched_supplier.get("total_cost_spot"),
            0.0,
        )
        spot_unit_price = _safe_float(
            enriched_supplier.get(
                "spot_price_used",
                enriched_supplier.get("spot_price"),
            ),
            0.0,
        )
        original_contract_lead = _safe_int(
            enriched_supplier.get(
                "current_lead_time"
            ),
            default=30,
        )

        cost_delta = (
            spot_total - contracted_total
        )
        cost_delta_pct = (
            (
                cost_delta
                / contracted_total
            )
            * 100
            if contracted_total
            else 0.0
        )

        enriched_supplier[
            "item_standard_lead_time_days"
        ] = item_standard_lead_time
        enriched_supplier[
            "estimated_spot_lead_time_days"
        ] = item_standard_lead_time
        enriched_supplier[
            "original_contract_lead_time_days"
        ] = original_contract_lead
        enriched_supplier[
            "spot_lead_time_savings_days"
        ] = max(
            0,
            (
                original_contract_lead
                - item_standard_lead_time
            ),
        )
        enriched_supplier[
            "spot_unit_price"
        ] = spot_unit_price
        enriched_supplier[
            "cost_delta_vs_contracted"
        ] = round(cost_delta, 2)
        enriched_supplier[
            "cost_delta_pct_vs_contracted"
        ] = round(cost_delta_pct, 2)
        enriched_supplier[
            "spot_discount_applied"
        ] = False

        enriched_suppliers.append(
            enriched_supplier
        )

    return enriched_suppliers


def _supplier_context(
    supplier: Dict[str, Any],
    available_days: int,
) -> str:
    spot_lead_time = supplier.get(
        "item_standard_lead_time_days"
    )
    timeline_feasible = (
        _safe_int(
            spot_lead_time,
            30,
        )
        + SPOT_BUFFER_DAYS
        <= available_days
    )

    return f"""
Supplier: {supplier.get('supplier_name')} ({supplier.get('supplier_id')})
- Risk Level: {supplier.get('risk_level')}
- Capacity: {supplier.get('capacity_status')}
- On-time Delivery: {supplier.get('on_time_delivery_pct')}%
- Quality Rejection: {supplier.get('quality_rejection_pct')}%
- Original Contract Lead Time: {supplier.get('original_contract_lead_time_days')} days
- ITEM STANDARD SPOT LEAD TIME: {spot_lead_time} days
- Spot Buffer Days: {SPOT_BUFFER_DAYS}
- Spot Timeline Feasible Including Buffer: {timeline_feasible}
- Available Days: {available_days}
- Spot Lead Time Savings vs Contract: {supplier.get('spot_lead_time_savings_days')} days
- Contracted Unit Price After Discount: {supplier.get('contracted_price_after_discount', supplier.get('contracted_price'))}
- Spot Unit Price: {supplier.get('spot_unit_price')}
- MOQ: {supplier.get('moq')}
- Recommended Order Qty (Batch): {supplier.get('recommended_order_quantity')}
- Total Cost Contracted: {supplier.get('total_cost_contracted')}
- Total Cost Spot: {supplier.get('total_cost_spot')}
- Spot Cost Delta vs Contracted: {supplier.get('cost_delta_vs_contracted')} ({supplier.get('cost_delta_pct_vs_contracted')}%)
- Overage Quantity: {supplier.get('overage_quantity')}
- Spot Discount Applied: False
"""


def _build_spot_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a disciplined spot-market procurement decision engine.

For a given item, every supplier must use the same ITEM STANDARD SPOT LEAD
TIME supplied in the data. Supplier-specific original contract lead time is
reference data only.

Spot procurement is intended for schedule recovery or business continuity.

Decision priority:
1. Timeline feasibility using ITEM STANDARD SPOT LEAD TIME plus the supplied
   spot buffer.
2. Supplier risk, capacity, on-time delivery, and quality.
3. Spot total cost and cost delta versus contracted.
4. MOQ overage and inventory impact.

Strict rules:
- Use Total Cost Spot for total_cost and total_spot_cost.
- Use Spot Unit Price for effective_unit_price and spot_unit_price.
- Set lead_time_days equal to item_standard_lead_time_days.
- Set bulk_discount_applied to false.
- Never apply a bulk or volume discount to spot procurement.
- Never use original contract lead time as the spot lead time.
- can_deliver_on_time must match Spot Timeline Feasible Including Buffer.
- Verify every cheaper/more-expensive statement against the supplied totals.
- When all suppliers share the same spot lead time, do not claim one supplier
  is faster than another.
- Return all non-selected suppliers in alternatives_considered.
- Never invent or reverse supplied metrics.
- Return only the required structured output.""",
        ),
        (
            "human",
            """Item: {item_name} ({item_id})
Gross Requirement: {gross_requirement}
Required Date: {required_date}
Available Days until Required Date: {available_days}
Item Standard Spot Lead Time: {item_standard_lead} days
Spot Buffer Days: {buffer_days}

Spot Strategy Supplier Data:
{suppliers_data}

Return the required structured analysis.""",
        ),
    ])


@traceable_if_enabled(
    name="Spot Supplier Item Reasoning",
    run_type="chain",
    tags=["procurement", "spot-reasoning", "item"],
)
def _reason_for_spot_item(
    *,
    item_id: str,
    item_name: str,
    gross_requirement: float,
    required_date: str,
    available_days: int,
    item_standard_lead: int,
    suppliers: List[Dict[str, Any]],
) -> SpotReasoningOutput:
    llm = ChatOpenAI(
        model=SPOT_REASONING_MODEL,
        temperature=0.0,
    )
    structured_llm = llm.with_structured_output(
        SpotReasoningOutput
    )
    chain = _build_spot_prompt() | structured_llm

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
        "item_standard_lead": (
            item_standard_lead
        ),
        "buffer_days": SPOT_BUFFER_DAYS,
        "suppliers_data": suppliers_data,
    })


def _build_spot_product_summary(
    *,
    item_results: List[SpotReasoningOutput],
    required_date: str,
    available_days: int,
) -> SpotProductLevelSummary:
    if not item_results:
        return SpotProductLevelSummary(
            critical_path_days=0,
            suggested_realistic_date="N/A",
            is_original_date_feasible=False,
            overall_message=(
                "No spot supplier options to analyze."
            ),
            chosen_suppliers_summary=[],
            total_procurement_cost=0.0,
            total_spot_procurement_cost=0.0,
            spot_strategy_assessment=(
                "No spot strategy assessment available."
            ),
        )

    critical_path = max(
        result.recommended_supplier.lead_time_days
        for result in item_results
    )
    days_required_with_buffer = (
        critical_path + SPOT_BUFFER_DAYS
    )
    suggested_date = _calculate_suggested_date(
        critical_path,
        buffer_days=SPOT_BUFFER_DAYS,
    )
    is_feasible = (
        days_required_with_buffer
        <= available_days
    )

    total_spot_cost = 0.0
    chosen_summary = []
    any_spot_recovery = False

    for result in item_results:
        recommendation = result.recommended_supplier
        total_spot_cost += (
            recommendation.total_spot_cost
        )

        if (
            recommendation.lead_time_days
            < recommendation.original_contract_lead_time_days
        ):
            any_spot_recovery = True

        chosen_summary.append({
            "item_id": result.item_id,
            "item_name": result.item_name,
            "supplier_name": (
                recommendation.supplier_name
            ),
            "order_quantity": (
                recommendation.overage_quantity
                + result.gross_requirement
            ),
            "lead_time_days": (
                recommendation.lead_time_days
            ),
            "estimated_spot_lead_time_days": (
                recommendation.lead_time_days
            ),
            "original_contract_lead_time_days": (
                recommendation.original_contract_lead_time_days
            ),
            "cost": recommendation.total_spot_cost,
            "spot_cost": (
                recommendation.total_spot_cost
            ),
            "cost_delta_vs_contracted": (
                recommendation.cost_delta_vs_contracted
            ),
            "buffer_days": SPOT_BUFFER_DAYS,
            "days_required_with_buffer": (
                days_required_with_buffer
            ),
        })

    if is_feasible:
        overall_message = (
            "Spot procurement can meet the required date "
            f"of {required_date} including a "
            f"{SPOT_BUFFER_DAYS}-day buffer."
        )
    else:
        overall_message = (
            "Spot procurement does not fully meet the "
            f"required date of {required_date} after applying "
            f"a {SPOT_BUFFER_DAYS}-day buffer. A realistic "
            f"fulfillment date is around {suggested_date}."
        )

    return SpotProductLevelSummary(
        critical_path_days=critical_path,
        suggested_realistic_date=suggested_date,
        is_original_date_feasible=is_feasible,
        overall_message=overall_message,
        chosen_suppliers_summary=chosen_summary,
        total_procurement_cost=round(
            total_spot_cost,
            2,
        ),
        total_spot_procurement_cost=round(
            total_spot_cost,
            2,
        ),
        spot_strategy_assessment=(
            "Spot strategy provides timeline recovery value."
            if any_spot_recovery
            else (
                "Spot strategy does not materially improve "
                "timeline based on available data."
            )
        ),
    )


def reason_with_spot_strategy(
    supplier_intelligence_output: Dict[str, Any],
) -> FullSpotReasoningResult:
    """
    Recommend spot suppliers and build the product-level spot summary.

    The public function signature and output schema are preserved for the
    supervisor, decision aggregator, persistence, conversation, and UI.
    """
    if not isinstance(
        supplier_intelligence_output,
        dict,
    ):
        raise SupplierReasoningError(
            "Supplier intelligence output must be a dictionary.",
            component="spot_reasoning",
        )

    required_date = (
        supplier_intelligence_output.get(
            "required_date"
        )
        or "N/A"
    )
    available_days = _get_available_days(
        supplier_intelligence_output.get(
            "required_date"
        )
    )
    items = (
        supplier_intelligence_output.get(
            "items_analyzed",
            [],
        )
        or []
    )

    item_results: List[
        SpotReasoningOutput
    ] = []

    for item in items:
        item_id = item.get("item_id")
        item_name = item.get("item_name", "")
        gross_requirement = item.get(
            "gross_requirement",
            0,
        )
        item_standard_lead = (
            _get_item_standard_lead_time(item)
        )
        suppliers = (
            enrich_suppliers_for_spot_strategy(
                item
            )
        )

        if not suppliers:
            logger.warning(
                "spot_reasoning_item_skipped",
                component="spot_reasoning",
                status="completed_with_warning",
                payload={
                    "item_id": item_id,
                    "reason": "no_supplier_options",
                },
            )
            continue

        started_at = time.perf_counter()

        logger.info(
            "spot_item_reasoning_started",
            component="spot_reasoning",
            status="running",
            payload={
                "item_id": item_id,
                "supplier_count": len(suppliers),
                "item_standard_lead_time_days": (
                    item_standard_lead
                ),
                "model": SPOT_REASONING_MODEL,
            },
        )

        try:
            response = _reason_for_spot_item(
                item_id=item_id,
                item_name=item_name,
                gross_requirement=gross_requirement,
                required_date=required_date,
                available_days=available_days,
                item_standard_lead=(
                    item_standard_lead
                ),
                suppliers=suppliers,
            )
        except Exception as exc:
            logger.exception(
                "spot_item_reasoning_failed",
                error=exc,
                component="spot_reasoning",
                status="failed",
                duration_ms=(
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                payload={
                    "item_id": item_id,
                    "supplier_count": len(suppliers),
                    "item_standard_lead_time_days": (
                        item_standard_lead
                    ),
                    "model": SPOT_REASONING_MODEL,
                },
            )
            raise SupplierReasoningError(
                f"Spot supplier reasoning failed for item {item_id}.",
                component="spot_reasoning",
            ) from exc

        item_results.append(response)

        logger.info(
            "spot_item_reasoning_completed",
            component="spot_reasoning",
            status="success",
            duration_ms=(
                time.perf_counter()
                - started_at
            )
            * 1000,
            payload={
                "item_id": item_id,
                "selected_supplier": (
                    response.recommended_supplier.supplier_name
                ),
                "supplier_count": len(suppliers),
                "item_standard_lead_time_days": (
                    item_standard_lead
                ),
                "model": SPOT_REASONING_MODEL,
            },
        )

    product_summary = (
        _build_spot_product_summary(
            item_results=item_results,
            required_date=required_date,
            available_days=available_days,
        )
    )

    return FullSpotReasoningResult(
        items=item_results,
        product_level=product_summary,
    )
