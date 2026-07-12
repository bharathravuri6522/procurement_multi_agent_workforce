"""
Demand and inventory analysis for a product-level procurement request.

The analyst expands the product BOM, checks item inventory, and calculates
the net quantity that must be procured for each component.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Optional

from agent_tools import (
    calculate_net_requirement,
    get_bom_items,
    get_inventory_status,
    get_product_details,
)
from core.exceptions import DemandAnalysisError
from core.logging import get_logger


DEMAND_ANALYST_VERSION = "demand_inventory_analyst_v2 | production-clean"
logger = get_logger("demand_inventory_analyst")


def _validate_inputs(
    product_id: str,
    demand_forecast: Optional[float],
) -> None:
    if not product_id or not product_id.strip():
        raise DemandAnalysisError(
            "Product ID is required for demand analysis.",
            component="demand_inventory_analyst",
        )

    if demand_forecast is None:
        return

    try:
        quantity = float(demand_forecast)
    except (TypeError, ValueError) as exc:
        raise DemandAnalysisError(
            "Demand forecast must be a valid number.",
            component="demand_inventory_analyst",
        ) from exc

    if quantity <= 0:
        raise DemandAnalysisError(
            "Demand forecast must be greater than zero.",
            component="demand_inventory_analyst",
        )


def _default_inventory_status(
    item_id: str,
    bom_item: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "item_id": item_id,
        "current_stock": 0,
        "reserved_qty": 0,
        "on_order_qty": 0,
        "available_qty": 0,
        "safety_stock": bom_item.get("safety_stock", 0),
        "lead_time_days": bom_item.get("lead_time_days", 0),
    }


def analyze_demand_and_inventory(
    product_id: str,
    demand_forecast: Optional[float] = None,
    required_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Expand a product BOM and calculate item-level procurement requirements.

    The return structure is intentionally preserved because downstream
    supplier-intelligence, planner, persistence, and UI modules depend on it.
    """
    _validate_inputs(product_id, demand_forecast)

    analysis: Dict[str, Any] = {
        "product_id": product_id,
        "analysis_timestamp": datetime.now().isoformat(),
        "required_date": required_date,
        "product_details": None,
        "bom_items": [],
        "item_analysis": [],
        "items_requiring_procurement": [],
        "summary": {},
    }

    try:
        product_info = get_product_details(product_id)
    except Exception as exc:
        logger.exception(
            "product_lookup_failed",
            error=exc,
            component="demand_inventory_analyst",
            status="failed",
            payload={"product_id": product_id},
        )
        raise DemandAnalysisError(
            f"Product lookup failed for {product_id}.",
            component="demand_inventory_analyst",
        ) from exc

    analysis["product_details"] = product_info

    if not product_info:
        analysis["error"] = (
            f"Product {product_id} not found in database."
        )
        logger.warning(
            "product_not_found",
            component="demand_inventory_analyst",
            status="completed_with_error",
            payload={"product_id": product_id},
        )
        return analysis

    try:
        bom_items = get_bom_items(product_id)
    except Exception as exc:
        logger.exception(
            "bom_lookup_failed",
            error=exc,
            component="demand_inventory_analyst",
            status="failed",
            payload={"product_id": product_id},
        )
        raise DemandAnalysisError(
            f"BOM lookup failed for product {product_id}.",
            component="demand_inventory_analyst",
        ) from exc

    analysis["bom_items"] = bom_items

    if not bom_items:
        analysis["warning"] = (
            f"No BOM found for product {product_id}. "
            "Treating product_id as a single item."
        )
        bom_items = [{
            "item_id": product_id,
            "item_name": product_info.get("name", product_id),
            "quantity": 1.0,
            "unit": "EA",
            "buffer_pct": 0.0,
            "safety_stock": 0,
        }]

        logger.warning(
            "bom_fallback_applied",
            component="demand_inventory_analyst",
            status="completed_with_warning",
            payload={"product_id": product_id},
        )

    total_net_requirement = 0.0
    items_needing_buy = []

    for bom_item in bom_items:
        item_id = bom_item["item_id"]

        try:
            inventory_status = get_inventory_status(item_id)
        except Exception as exc:
            logger.exception(
                "inventory_lookup_failed",
                error=exc,
                component="demand_inventory_analyst",
                status="failed",
                payload={
                    "product_id": product_id,
                    "item_id": item_id,
                },
            )
            raise DemandAnalysisError(
                f"Inventory lookup failed for item {item_id}.",
                component="demand_inventory_analyst",
            ) from exc

        if not inventory_status:
            inventory_status = _default_inventory_status(
                item_id,
                bom_item,
            )
            logger.warning(
                "inventory_default_applied",
                component="demand_inventory_analyst",
                status="completed_with_warning",
                payload={
                    "product_id": product_id,
                    "item_id": item_id,
                },
            )

        bom_quantity = bom_item.get("quantity", 1.0)
        buffer_pct = bom_item.get("buffer_pct", 0) or 0.0

        base_requirement = (
            bom_quantity
            if demand_forecast is None
            else demand_forecast * bom_quantity
        )
        buffer_requirement = base_requirement * buffer_pct
        gross_requirement = math.ceil(
            base_requirement + buffer_requirement
        )

        safety_stock = (
            inventory_status.get("safety_stock", 0) or 0
        )
        current_stock = (
            inventory_status.get("current_stock", 0) or 0
        )
        on_order_quantity = (
            inventory_status.get("on_order_qty", 0) or 0
        )

        try:
            net_requirement = calculate_net_requirement(
                demand_forecast=gross_requirement,
                current_stock=current_stock,
                safety_stock=safety_stock,
                on_order_qty=on_order_quantity,
            )
        except Exception as exc:
            logger.exception(
                "net_requirement_calculation_failed",
                error=exc,
                component="demand_inventory_analyst",
                status="failed",
                payload={
                    "product_id": product_id,
                    "item_id": item_id,
                    "gross_requirement": gross_requirement,
                },
            )
            raise DemandAnalysisError(
                f"Net requirement calculation failed for item {item_id}.",
                component="demand_inventory_analyst",
            ) from exc

        item_result = {
            "item_id": item_id,
            "item_name": bom_item.get("item_name", item_id),
            "bom_quantity": bom_quantity,
            "base_requirement": base_requirement,
            "buffer_pct": buffer_pct,
            "buffer_requirement": buffer_requirement,
            "gross_requirement": gross_requirement,
            "inventory_status": inventory_status,
            "net_requirement": net_requirement,
            "needs_procurement": net_requirement > 0,
        }

        analysis["item_analysis"].append(item_result)

        if net_requirement > 0:
            items_needing_buy.append(item_result)
            total_net_requirement += net_requirement

    analysis["items_requiring_procurement"] = items_needing_buy
    analysis["summary"] = {
        "total_items_in_bom": len(bom_items),
        "items_requiring_procurement": len(items_needing_buy),
        "total_net_requirement_across_items": round(
            total_net_requirement,
            2,
        ),
        "has_sufficient_inventory": len(items_needing_buy) == 0,
    }

    return analysis
