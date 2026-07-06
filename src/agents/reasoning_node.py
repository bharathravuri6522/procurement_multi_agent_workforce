"""
Reasoning Node

This module handles intelligent analysis of supplier options using LLM
with structured output. It supports per-item reasoning + product-level
critical path calculation (Phase 1).
"""

import os
from typing import Dict, Any, List
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()


# ============================================================
# PYDANTIC MODELS (Structured Output)
# ============================================================

class RecommendedSupplier(BaseModel):
    supplier_id: str
    supplier_name: str
    reasoning: str = Field(..., description="Detailed explanation covering cost, risk, lead time feasibility, overage impact, and alignment with required date")
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


# ============================================================
# HELPER: Calculate Available Days
# ============================================================

def get_available_days(required_date_str: str) -> int:
    try:
        required = datetime.strptime(required_date_str, "%Y-%m-%d").date()
        today = date.today()
        return max(0, (required - today).days)
    except:
        return 30  # fallback


def calculate_suggested_date(critical_path_days: int, buffer_days: int = 1) -> str:
    suggested = date.today() + timedelta(days=critical_path_days + buffer_days)
    return suggested.strftime("%Y-%m-%d")


# ============================================================
# REASONING NODE
# ============================================================

def reason_and_recommend(supplier_intelligence_output: Dict[str, Any]) -> FullReasoningResult:
    """
    Reasoning Node with improved timeline handling and Critical Path calculation.
    Returns both per-item recommendations and a product-level summary.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    structured_llm = llm.with_structured_output(ReasoningOutput)

    item_results = []
    available_days = get_available_days(
        supplier_intelligence_output.get("required_date", "2026-07-15")
    )

    for item in supplier_intelligence_output.get("items_analyzed", []):
        item_id = item["item_id"]
        item_name = item.get("item_name", "")
        gross_requirement = item["gross_requirement"]
        suppliers = item.get("suppliers", [])

        if not suppliers:
            continue

        suppliers_context = []
        for sup in suppliers:
            context = f"""
Supplier: {sup.get('supplier_name')} ({sup.get('supplier_id')})
- Risk Level: {sup.get('risk_level')}
- Lead Time: {sup.get('current_lead_time')} days
- On-time Delivery: {sup.get('on_time_delivery_pct')}% | Quality Rejection: {sup.get('quality_rejection_pct')}%
- Capacity: {sup.get('capacity_status')}
- Contracted Price: {sup.get('contracted_price')} | Spot Price: {sup.get('spot_price')}
- MOQ: {sup.get('moq')}
- Recommended Order Qty (Batch): {sup.get('recommended_order_quantity')}
- Total Cost (Contracted after discount): {sup.get('total_cost_contracted')}
- Total Cost (Spot): {sup.get('total_cost_spot')}
- Overage Quantity: {sup.get('overage_quantity')}
- Bulk Discount Applied: {sup.get('bulk_discount_applied')}
"""
            suppliers_context.append(context)

        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a highly disciplined procurement decision engine.

Your task is to recommend **exactly one** best supplier for the item using a strict priority order.

**Decision Priority (must follow in this exact order):**
1. **Timeline Feasibility** — Can the supplier realistically deliver by the required date? (Lead time ≤ available days is strongly preferred. If no supplier meets it, choose the one with the shortest lead time + best reliability.)
2. **Risk & Reliability** — Prioritize Low risk, high on-time delivery %, low quality rejection %.
3. **Total Cost** — After applying bulk discount (if any) and considering overage cost.
4. **Inventory Impact** — Lower overage is better.

**Strict Rules:**
- You must follow the priority order above. Do not randomly pick when options are close.
- Be consistent. For the same input data, you should give the same recommendation every time.
- If no supplier can meet the required date, clearly state this in the reasoning but still pick the best feasible option based on the priorities.
- Never invent data. Only use the information provided.

Think step by step internally before outputting the final structured answer."""),
            ("human", """
Item: {item_name} ({item_id})
Gross Requirement: {gross_requirement}
Required Date: {required_date}
Available Days until Required Date: {available_days}

Suppliers Data:
{suppliers_data}

Provide your analysis in the required structured JSON format.
""")
        ])

        chain = prompt | structured_llm

        try:
            response = chain.invoke({
                "item_name": item_name,
                "item_id": item_id,
                "gross_requirement": gross_requirement,
                "required_date": supplier_intelligence_output.get("required_date", "2026-07-15"),
                "available_days": available_days,
                "suppliers_data": "\n".join(suppliers_context)
            })
            item_results.append(response)
        except Exception as e:
            print(f"Error processing item {item_id}: {e}")

    # ============================================================
    # Product Level Summary (Critical Path + Chosen Suppliers + Total Cost)
    # ============================================================
    if item_results:
        critical_path = max(r.recommended_supplier.lead_time_days for r in item_results)
        suggested_date = calculate_suggested_date(critical_path, buffer_days=1)
        is_feasible = critical_path <= available_days

        if is_feasible:
            message = f"All items can be procured within the required date of {supplier_intelligence_output.get('required_date')}."
        else:
            message = f"The original required date is not feasible. A realistic fulfillment date would be around {suggested_date}."

        # Build chosen suppliers summary + total cost
        chosen_summary = []
        total_cost = 0.0

        for r in item_results:
            rec = r.recommended_supplier
            chosen_summary.append({
                "item_id": r.item_id,
                "item_name": r.item_name,
                "supplier_name": rec.supplier_name,
                "order_quantity": rec.overage_quantity + r.gross_requirement,  # Approximate
                "lead_time_days": rec.lead_time_days,
                "cost": rec.total_cost
            })
            total_cost += rec.total_cost

        product_summary = ProductLevelSummary(
            critical_path_days=critical_path,
            suggested_realistic_date=suggested_date,
            is_original_date_feasible=is_feasible,
            overall_message=message,
            chosen_suppliers_summary=chosen_summary,
            total_procurement_cost=round(total_cost, 2)
        )
    else:
        product_summary = ProductLevelSummary(
            critical_path_days=0,
            suggested_realistic_date="N/A",
            is_original_date_feasible=False,
            overall_message="No items to analyze.",
            chosen_suppliers_summary=[],
            total_procurement_cost=0.0
        )

    return FullReasoningResult(
        items=item_results,
        product_level=product_summary
    )