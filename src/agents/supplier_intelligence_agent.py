"""
Supplier intelligence and deterministic supplier-cost enrichment.

This module prepares contracted and spot procurement context for downstream
reasoning. It does not select a supplier.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict

try:
    from agent_tools_v2 import get_supplier_options
except ImportError:
    from agent_tools import get_supplier_options

from core.exceptions import SupplierIntelligenceError
from core.logging import get_logger


SUPPLIER_INTELLIGENCE_VERSION = (
    "supplier_intelligence_agent_v3 | production-clean"
)

logger = get_logger("supplier_intelligence_agent")


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


def calculate_supplier_costs(
    supplier: Dict[str, Any],
    gross_requirement: float,
) -> Dict[str, Any]:
    """
    Calculate contracted and spot procurement costs deterministically.

    Contracted pricing:
    - MOQ rounding applies.
    - Volume discounts apply only when the rounded order quantity reaches the
      configured threshold.

    Spot pricing:
    - MOQ rounding applies.
    - Volume discounts never apply.
    """
    contracted_price = _safe_float(
        supplier.get("contracted_price"),
        0.0,
    )
    spot_price = _safe_float(
        supplier.get("spot_price"),
        0.0,
    )
    moq = _safe_int(
        supplier.get("moq"),
        1,
    ) or 1
    volume_discount_pct = _safe_float(
        supplier.get("volume_discount_pct"),
        0.0,
    )
    volume_threshold = _safe_int(
        supplier.get("volume_threshold"),
        0,
    )
    normalized_requirement = _safe_float(
        gross_requirement,
        0.0,
    )

    if normalized_requirement <= 0:
        recommended_quantity = 0
    else:
        recommended_quantity = int(
            math.ceil(normalized_requirement / moq) * moq
        )

    bulk_discount_eligible = (
        recommended_quantity > 0
        and volume_threshold > 0
        and recommended_quantity >= volume_threshold
        and volume_discount_pct > 0
    )

    if bulk_discount_eligible:
        discounted_contract_price = contracted_price * (
            1 - volume_discount_pct / 100
        )
        bulk_discount_amount = (
            recommended_quantity
            * contracted_price
            * (volume_discount_pct / 100)
        )
    else:
        discounted_contract_price = contracted_price
        bulk_discount_amount = 0.0

    total_cost_contracted = (
        recommended_quantity * discounted_contract_price
    )

    # Spot pricing intentionally does not receive a volume discount.
    total_cost_spot = recommended_quantity * spot_price

    overage_quantity = max(
        0.0,
        recommended_quantity - normalized_requirement,
    )
    overage_cost_contracted = (
        overage_quantity * discounted_contract_price
    )
    overage_cost_spot = overage_quantity * spot_price

    effective_unit_price_contracted = (
        total_cost_contracted / recommended_quantity
        if recommended_quantity > 0
        else 0.0
    )
    effective_unit_price_spot = (
        total_cost_spot / recommended_quantity
        if recommended_quantity > 0
        else 0.0
    )

    bulk_discount_shortfall_quantity = 0

    if volume_threshold > 0 and not bulk_discount_eligible:
        bulk_discount_shortfall_quantity = max(
            0,
            volume_threshold - recommended_quantity,
        )

    spot_vs_contracted_delta = (
        total_cost_spot - total_cost_contracted
    )
    spot_vs_contracted_delta_pct = (
        (
            spot_vs_contracted_delta
            / total_cost_contracted
        )
        * 100
        if total_cost_contracted
        else 0.0
    )

    return {
        "moq_used_as_batch_size": moq,
        "recommended_order_quantity": recommended_quantity,
        "overage_quantity": round(overage_quantity, 2),

        "contracted_price_before_discount": round(
            contracted_price,
            4,
        ),
        "contracted_price_after_discount": round(
            discounted_contract_price,
            4,
        ),
        "total_cost_contracted": round(
            total_cost_contracted,
            2,
        ),
        "effective_unit_price_contracted": round(
            effective_unit_price_contracted,
            4,
        ),
        "overage_cost_contracted": round(
            overage_cost_contracted,
            2,
        ),

        "spot_price_used": round(
            spot_price,
            4,
        ),
        "total_cost_spot": round(
            total_cost_spot,
            2,
        ),
        "effective_unit_price_spot": round(
            effective_unit_price_spot,
            4,
        ),
        "overage_cost_spot": round(
            overage_cost_spot,
            2,
        ),
        "spot_discount_applied": False,

        "volume_threshold": volume_threshold,
        "volume_discount_pct": round(
            volume_discount_pct,
            4,
        ),
        "bulk_discount_applied": bulk_discount_eligible,
        "bulk_discount_amount": round(
            bulk_discount_amount,
            2,
        ),
        "bulk_discount_shortfall_qty": (
            bulk_discount_shortfall_quantity
        ),

        "spot_vs_contracted_delta": round(
            spot_vs_contracted_delta,
            2,
        ),
        "spot_vs_contracted_delta_pct": round(
            spot_vs_contracted_delta_pct,
            2,
        ),
    }


def recommend_suppliers(
    analysis_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Collect and enrich supplier options for every item requiring procurement.

    The returned structure is preserved because planner, reasoning, persistence,
    conversation, and UI modules depend on these fields.
    """
    if not isinstance(analysis_result, dict):
        raise SupplierIntelligenceError(
            "Demand analysis output must be a dictionary.",
            component="supplier_intelligence_agent",
        )

    output: Dict[str, Any] = {
        "product_id": analysis_result.get("product_id"),
        "required_date": analysis_result.get("required_date"),
        "analysis_timestamp": datetime.now().isoformat(),
        "items_analyzed": [],
        "summary": {},
    }

    item_analysis = (
        analysis_result.get("item_analysis", []) or []
    )
    items_needing_procurement = [
        item
        for item in item_analysis
        if item.get("needs_procurement")
    ]

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
        gross_requirement = item.get(
            "gross_requirement",
            item.get("net_requirement", 0),
        )

        try:
            raw_suppliers = get_supplier_options(item_id)
        except Exception as exc:
            logger.exception(
                "supplier_options_lookup_failed",
                error=exc,
                component="supplier_intelligence_agent",
                status="failed",
                payload={
                    "product_id": output.get("product_id"),
                    "item_id": item_id,
                },
            )
            raise SupplierIntelligenceError(
                f"Supplier lookup failed for item {item_id}.",
                component="supplier_intelligence_agent",
            ) from exc

        raw_suppliers = raw_suppliers or []
        enriched_suppliers = []

        for supplier in raw_suppliers:
            try:
                cost_data = calculate_supplier_costs(
                    supplier=supplier,
                    gross_requirement=gross_requirement,
                )
            except Exception as exc:
                logger.exception(
                    "supplier_cost_enrichment_failed",
                    error=exc,
                    component="supplier_intelligence_agent",
                    status="failed",
                    payload={
                        "product_id": output.get("product_id"),
                        "item_id": item_id,
                        "supplier_id": supplier.get("supplier_id"),
                    },
                )
                raise SupplierIntelligenceError(
                    (
                        "Supplier cost enrichment failed for "
                        f"item {item_id}."
                    ),
                    component="supplier_intelligence_agent",
                ) from exc

            enriched_suppliers.append({
                **supplier,
                **cost_data,
            })

        if not enriched_suppliers:
            logger.warning(
                "no_supplier_options_found",
                component="supplier_intelligence_agent",
                status="completed_with_warning",
                payload={
                    "product_id": output.get("product_id"),
                    "item_id": item_id,
                },
            )

        total_supplier_options += len(enriched_suppliers)

        inventory_status = (
            item.get("inventory_status") or {}
        )

        item_standard_lead_time_days = None

        if enriched_suppliers:
            item_standard_lead_time_days = (
                enriched_suppliers[0].get(
                    "item_standard_lead_time_days"
                )
            )

        if item_standard_lead_time_days in (
            None,
            "",
            "Not available",
        ):
            item_standard_lead_time_days = (
                inventory_status.get("lead_time_days")
            )

        item_result = {
            "item_id": item_id,
            "item_name": item.get("item_name"),
            "gross_requirement": gross_requirement,
            "net_requirement": item.get("net_requirement"),
            "base_requirement": item.get("base_requirement"),
            "buffer_pct": item.get("buffer_pct"),
            "buffer_requirement": item.get(
                "buffer_requirement"
            ),
            "inventory_status": inventory_status,
            "item_standard_lead_time_days": (
                item_standard_lead_time_days
            ),
            "suppliers": enriched_suppliers,
            "supplier_count": len(enriched_suppliers),
            "item_unit_cost": (
                enriched_suppliers[0].get("item_unit_cost")
                if enriched_suppliers
                else None
            ),
            "item_spot_price_threshold": (
                enriched_suppliers[0].get(
                    "item_spot_price_threshold"
                )
                if enriched_suppliers
                else None
            ),
        }

        output["items_analyzed"].append(item_result)

    output["summary"] = {
        "total_items_needing_procurement": len(
            items_needing_procurement
        ),
        "total_supplier_options": total_supplier_options,
        "message": (
            "Collected and enriched supplier data for "
            f"{len(output['items_analyzed'])} items."
        ),
    }

    return output
