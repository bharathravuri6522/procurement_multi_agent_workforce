"""
Spot Reasoning Node v2

Corrected design:
- Spot path uses item-level standard lead time from items.lead_time_days.
- Spot path does NOT use supplier-specific contracted/current lead time for feasibility.
- Spot path does NOT apply bulk/volume discounts.
- Supplier choice still considers risk, reliability, capacity, spot cost, MOQ overage, and inventory impact.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

load_dotenv()


class SpotRecommendedSupplier(BaseModel):
    supplier_id: str
    supplier_name: str
    reasoning: str = Field(..., description="Why this supplier was chosen for spot procurement.")

    # Generic fields so existing loggers can display spot output without N/A.
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


def _get_available_days(required_date_str: str) -> int:
    try:
        required = datetime.strptime(required_date_str, "%Y-%m-%d").date()
        return max(0, (required - date.today()).days)
    except Exception:
        return 30


def _calculate_suggested_date(critical_path_days: int, buffer_days: int = 1) -> str:
    return (date.today() + timedelta(days=critical_path_days + buffer_days)).strftime("%Y-%m-%d")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "Not available"):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "Not available"):
            return default
        return int(float(value))
    except Exception:
        return default


def _get_item_standard_lead_time(item: Dict[str, Any]) -> int:
    value = item.get("item_standard_lead_time_days")
    if value not in (None, "", "Not available"):
        return _safe_int(value, default=30)

    inventory_status = item.get("inventory_status") or {}
    value = inventory_status.get("lead_time_days")
    return _safe_int(value, default=30)


def enrich_suppliers_for_spot_strategy(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Attach spot-strategy fields using item-level lead time only."""
    item_standard_lead_time = _get_item_standard_lead_time(item)
    enriched: List[Dict[str, Any]] = []

    for supplier in item.get("suppliers", []) or []:
        s = dict(supplier)

        contracted_total = _safe_float(s.get("total_cost_contracted"), 0.0)
        spot_total = _safe_float(s.get("total_cost_spot"), 0.0)
        spot_unit = _safe_float(s.get("spot_price_used", s.get("spot_price")), 0.0)
        original_contract_lead = _safe_int(s.get("current_lead_time"), default=30)

        cost_delta = spot_total - contracted_total
        cost_delta_pct = (cost_delta / contracted_total * 100) if contracted_total else 0.0

        s["item_standard_lead_time_days"] = item_standard_lead_time
        s["estimated_spot_lead_time_days"] = item_standard_lead_time
        s["original_contract_lead_time_days"] = original_contract_lead
        s["spot_lead_time_savings_days"] = max(0, original_contract_lead - item_standard_lead_time)
        s["spot_unit_price"] = spot_unit
        s["cost_delta_vs_contracted"] = round(cost_delta, 2)
        s["cost_delta_pct_vs_contracted"] = round(cost_delta_pct, 2)
        s["spot_discount_applied"] = False
        enriched.append(s)

    return enriched


def reason_with_spot_strategy(supplier_intelligence_output: Dict[str, Any]) -> FullSpotReasoningResult:
    required_date = supplier_intelligence_output.get("required_date", "2026-07-15")
    available_days = _get_available_days(required_date)

    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    structured_llm = llm.with_structured_output(SpotReasoningOutput)

    item_results: List[SpotReasoningOutput] = []

    for item in supplier_intelligence_output.get("items_analyzed", []) or []:
        item_id = item.get("item_id")
        item_name = item.get("item_name", "")
        gross_requirement = item.get("gross_requirement", 0)
        item_standard_lead = _get_item_standard_lead_time(item)
        suppliers = enrich_suppliers_for_spot_strategy(item)

        if not suppliers:
            continue

        suppliers_context = []
        for sup in suppliers:
            context = f"""
Supplier: {sup.get('supplier_name')} ({sup.get('supplier_id')})
- Risk Level: {sup.get('risk_level')}
- Capacity: {sup.get('capacity_status')}
- On-time Delivery: {sup.get('on_time_delivery_pct')}% | Quality Rejection: {sup.get('quality_rejection_pct')}%
- Original Contract Lead Time: {sup.get('original_contract_lead_time_days')} days
- ITEM STANDARD SPOT LEAD TIME: {sup.get('item_standard_lead_time_days')} days
- Spot Lead Time Savings vs Contract: {sup.get('spot_lead_time_savings_days')} days
- Contracted Unit Price After Discount: {sup.get('contracted_price_after_discount', sup.get('contracted_price'))}
- Spot Unit Price: {sup.get('spot_unit_price')}
- MOQ: {sup.get('moq')}
- Recommended Order Qty (Batch): {sup.get('recommended_order_quantity')}
- Total Cost Contracted: {sup.get('total_cost_contracted')}
- Total Cost Spot: {sup.get('total_cost_spot')}
- Spot Cost Delta vs Contracted: {sup.get('cost_delta_vs_contracted')} ({sup.get('cost_delta_pct_vs_contracted')}%)
- Overage Quantity: {sup.get('overage_quantity')}
- Spot Discount Applied: False
"""
            suppliers_context.append(context)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a disciplined spot-market procurement decision engine.

Important rule: For spot procurement, every supplier for the same item uses the ITEM STANDARD SPOT LEAD TIME provided in the supplier data. Do not invent or estimate a different spot lead time.

Spot procurement is used for schedule recovery or business continuity. It should be recommended only when it improves feasibility or provides acceptable emergency procurement value.

Decision priority:
1. Timeline feasibility using ITEM STANDARD SPOT LEAD TIME.
2. Supplier risk, capacity, on-time delivery, and quality.
3. Spot total cost and spot cost delta vs contracted.
4. MOQ/overage and inventory impact.

Strict rules:
- Use Total Cost Spot for total_cost and total_spot_cost.
- Use Spot Unit Price for effective_unit_price and spot_unit_price.
- Set lead_time_days equal to item_standard_lead_time_days.
- Set bulk_discount_applied to false because spot orders do not receive volume discounts.
- Never use original contract lead time as the spot lead time.
- Never invent data.
""",
                ),
                (
                    "human",
                    """
Item: {item_name} ({item_id})
Gross Requirement: {gross_requirement}
Required Date: {required_date}
Available Days until Required Date: {available_days}
Item Standard Spot Lead Time: {item_standard_lead} days

Spot Strategy Supplier Data:
{suppliers_data}

Return the required structured output.
""",
                ),
            ]
        )

        chain = prompt | structured_llm

        try:
            response = chain.invoke(
                {
                    "item_name": item_name,
                    "item_id": item_id,
                    "gross_requirement": gross_requirement,
                    "required_date": required_date,
                    "available_days": available_days,
                    "item_standard_lead": item_standard_lead,
                    "suppliers_data": "\n".join(suppliers_context),
                }
            )
            item_results.append(response)
        except Exception as e:
            print(f"Error processing spot reasoning for item {item_id}: {e}")

    if item_results:
        critical_path = max(r.recommended_supplier.lead_time_days for r in item_results)
        buffer_days = 1
        days_required_with_buffer = critical_path + buffer_days
        suggested_date = _calculate_suggested_date(critical_path, buffer_days=buffer_days)

        # Feasibility must use the same buffer policy as suggested_realistic_date.
        # If critical path is 8 days and buffer is 1 day, then the strategy needs
        # 9 calendar days from today; it should not be marked feasible for an
        # 8-day requirement.
        is_feasible = days_required_with_buffer <= available_days

        total_spot_cost = 0.0
        chosen_summary = []
        any_spot_recovery = False

        for r in item_results:
            rec = r.recommended_supplier
            total_spot_cost += rec.total_spot_cost
            if rec.lead_time_days < rec.original_contract_lead_time_days:
                any_spot_recovery = True
            chosen_summary.append(
                {
                    "item_id": r.item_id,
                    "item_name": r.item_name,
                    "supplier_name": rec.supplier_name,
                    "order_quantity": rec.overage_quantity + r.gross_requirement,
                    "lead_time_days": rec.lead_time_days,
                    "estimated_spot_lead_time_days": rec.lead_time_days,
                    "original_contract_lead_time_days": rec.original_contract_lead_time_days,
                    "cost": rec.total_spot_cost,
                    "spot_cost": rec.total_spot_cost,
                    "cost_delta_vs_contracted": rec.cost_delta_vs_contracted,
                    "buffer_days": buffer_days,
                    "days_required_with_buffer": days_required_with_buffer,
                }
            )

        if is_feasible:
            overall_message = (
                f"Spot procurement can meet the required date of {required_date} "
                f"including a {buffer_days}-day buffer."
            )
        else:
            overall_message = (
                f"Spot procurement does not fully meet the required date of {required_date} "
                f"after applying a {buffer_days}-day buffer. A realistic fulfillment date is around {suggested_date}."
            )

        product_summary = SpotProductLevelSummary(
            critical_path_days=critical_path,
            suggested_realistic_date=suggested_date,
            is_original_date_feasible=is_feasible,
            overall_message=overall_message,
            chosen_suppliers_summary=chosen_summary,
            total_procurement_cost=round(total_spot_cost, 2),
            total_spot_procurement_cost=round(total_spot_cost, 2),
            spot_strategy_assessment=(
                "Spot strategy provides timeline recovery value."
                if any_spot_recovery
                else "Spot strategy does not materially improve timeline based on available data."
            ),
        )
    else:
        product_summary = SpotProductLevelSummary(
            critical_path_days=0,
            suggested_realistic_date="N/A",
            is_original_date_feasible=False,
            overall_message="No spot supplier options to analyze.",
            chosen_suppliers_summary=[],
            total_procurement_cost=0.0,
            total_spot_procurement_cost=0.0,
            spot_strategy_assessment="No spot strategy assessment available.",
        )

    return FullSpotReasoningResult(items=item_results, product_level=product_summary)
