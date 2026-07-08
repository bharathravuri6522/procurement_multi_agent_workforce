"""
Supplier Intelligence Agent v2

Purpose:
- Collect supplier options for each required item.
- Enrich every supplier with deterministic contracted and spot cost calculations.
- Keep contracted pricing and spot pricing logic separate and explicit.
- Expose volume discount thresholds so logs/reasoning can verify eligibility.

Design principles:
- Contracted pricing may receive volume discounts.
- Spot pricing does NOT receive volume discounts.
- MOQ is used as the batch-size rounding rule for both contracted and spot calculations.
- This node does NOT select the supplier; it prepares structured decision context.
"""

from typing import Dict, Any
from datetime import datetime
import math
import json

try:
    from agent_tools_v2 import get_supplier_options
except ImportError:
    from agent_tools import get_supplier_options


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "Not available"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "Not available"):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def calculate_supplier_costs(supplier: Dict[str, Any], gross_requirement: float) -> Dict[str, Any]:
    """
    Deterministic supplier cost calculation.

    Contracted path:
    - MOQ/batch rounding applies.
    - Volume discount applies only if recommended_order_quantity >= volume_threshold.

    Spot path:
    - MOQ/batch rounding applies.
    - No volume discount is applied.
    """
    contracted_price = _safe_float(supplier.get("contracted_price"), 0.0)
    spot_price = _safe_float(supplier.get("spot_price"), 0.0)
    moq = _safe_int(supplier.get("moq"), 1) or 1
    volume_discount_pct = _safe_float(supplier.get("volume_discount_pct"), 0.0)
    volume_threshold = _safe_int(supplier.get("volume_threshold"), 0)
    gross_requirement = _safe_float(gross_requirement, 0.0)

    if gross_requirement <= 0:
        recommended_qty = 0
    else:
        recommended_qty = int(math.ceil(gross_requirement / moq) * moq)

    bulk_discount_eligible = (
        recommended_qty > 0
        and volume_threshold > 0
        and recommended_qty >= volume_threshold
        and volume_discount_pct > 0
    )

    if bulk_discount_eligible:
        discounted_contract_price = contracted_price * (1 - volume_discount_pct / 100)
        bulk_discount_amount = recommended_qty * contracted_price * (volume_discount_pct / 100)
    else:
        discounted_contract_price = contracted_price
        bulk_discount_amount = 0.0

    # Contracted cost can receive discount.
    total_cost_contracted = recommended_qty * discounted_contract_price

    # Spot cost NEVER receives bulk/volume discount in this design.
    total_cost_spot = recommended_qty * spot_price

    overage_qty = max(0.0, recommended_qty - gross_requirement)
    overage_cost_contracted = overage_qty * discounted_contract_price
    overage_cost_spot = overage_qty * spot_price

    effective_unit_price_contracted = (
        total_cost_contracted / recommended_qty if recommended_qty > 0 else 0.0
    )
    effective_unit_price_spot = (
        total_cost_spot / recommended_qty if recommended_qty > 0 else 0.0
    )

    bulk_discount_shortfall_qty = 0
    if volume_threshold > 0 and not bulk_discount_eligible:
        bulk_discount_shortfall_qty = max(0, volume_threshold - recommended_qty)

    spot_vs_contracted_delta = total_cost_spot - total_cost_contracted
    spot_vs_contracted_delta_pct = (
        (spot_vs_contracted_delta / total_cost_contracted) * 100
        if total_cost_contracted else 0.0
    )

    return {
        "moq_used_as_batch_size": moq,
        "recommended_order_quantity": recommended_qty,
        "overage_quantity": round(overage_qty, 2),

        "contracted_price_before_discount": round(contracted_price, 4),
        "contracted_price_after_discount": round(discounted_contract_price, 4),
        "total_cost_contracted": round(total_cost_contracted, 2),
        "effective_unit_price_contracted": round(effective_unit_price_contracted, 4),
        "overage_cost_contracted": round(overage_cost_contracted, 2),

        "spot_price_used": round(spot_price, 4),
        "total_cost_spot": round(total_cost_spot, 2),
        "effective_unit_price_spot": round(effective_unit_price_spot, 4),
        "overage_cost_spot": round(overage_cost_spot, 2),
        "spot_discount_applied": False,

        "volume_threshold": volume_threshold,
        "volume_discount_pct": round(volume_discount_pct, 4),
        "bulk_discount_applied": bulk_discount_eligible,
        "bulk_discount_amount": round(bulk_discount_amount, 2),
        "bulk_discount_shortfall_qty": bulk_discount_shortfall_qty,

        "spot_vs_contracted_delta": round(spot_vs_contracted_delta, 2),
        "spot_vs_contracted_delta_pct": round(spot_vs_contracted_delta_pct, 2),
    }


def recommend_suppliers(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    output = {
        "product_id": analysis_result.get("product_id"),
        "required_date": analysis_result.get("required_date"),
        "analysis_timestamp": datetime.now().isoformat(),
        "items_analyzed": [],
        "summary": {},
    }

    item_analysis = analysis_result.get("item_analysis", []) or []
    items_needing_procurement = [item for item in item_analysis if item.get("needs_procurement")]

    if not items_needing_procurement:
        output["summary"] = {
            "total_items_needing_procurement": 0,
            "total_supplier_options": 0,
            "message": "No items require procurement.",
        }
        return output

    total_supplier_options = 0

    for item in items_needing_procurement:
        item_id = item["item_id"]
        gross_req = item.get("gross_requirement", item.get("net_requirement", 0))

        raw_suppliers = get_supplier_options(item_id)
        enriched_suppliers = []

        for supplier in raw_suppliers:
            cost_data = calculate_supplier_costs(supplier=supplier, gross_requirement=gross_req)
            enriched_supplier = {**supplier, **cost_data}
            enriched_suppliers.append(enriched_supplier)

        total_supplier_options += len(enriched_suppliers)

        inventory_status = item.get("inventory_status") or {}
        item_standard_lead_time_days = None
        if enriched_suppliers:
            item_standard_lead_time_days = enriched_suppliers[0].get("item_standard_lead_time_days")
        if item_standard_lead_time_days in (None, "", "Not available"):
            item_standard_lead_time_days = inventory_status.get("lead_time_days")

        item_result = {
            "item_id": item_id,
            "item_name": item.get("item_name"),
            "gross_requirement": gross_req,
            "net_requirement": item.get("net_requirement"),
            "base_requirement": item.get("base_requirement"),
            "buffer_pct": item.get("buffer_pct"),
            "buffer_requirement": item.get("buffer_requirement"),
            "inventory_status": inventory_status,
            "item_standard_lead_time_days": item_standard_lead_time_days,
            "suppliers": enriched_suppliers,
            "supplier_count": len(enriched_suppliers),
            "item_unit_cost": enriched_suppliers[0].get("item_unit_cost") if enriched_suppliers else None,
            "item_spot_price_threshold": enriched_suppliers[0].get("item_spot_price_threshold") if enriched_suppliers else None,
        }

        output["items_analyzed"].append(item_result)

    output["summary"] = {
        "total_items_needing_procurement": len(items_needing_procurement),
        "total_supplier_options": total_supplier_options,
        "message": f"Collected and enriched supplier data for {len(output['items_analyzed'])} items.",
    }

    return output


if __name__ == "__main__":
    from demand_inventory_analyst import analyze_demand_and_inventory

    demand_analysis = analyze_demand_and_inventory(
        product_id="RS-240",
        demand_forecast=80,
        required_date="2026-07-15",
    )
    supplier_output = recommend_suppliers(demand_analysis)
    print(json.dumps(supplier_output, indent=2, default=str))
