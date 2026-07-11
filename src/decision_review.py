"""
Decision Review Layer

Purpose:
- Preserve the AI procurement recommendation as immutable evidence.
- Apply human strategy/supplier overrides without rewriting the AI recommendation.
- Produce an effective procurement plan that can later be used for PR creation.

This module is deterministic and does not call an LLM.

Hybrid Strategy v2:
- Uses Spot critical path as the earliest achievable production window.
- Uses Contracted procurement for any item that can arrive within that same window.
- Uses Spot only where Contracted would delay the earliest achievable production start.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


REVIEW_LAYER_VERSION = "decision_review_v2 | critical-path-aware-hybrid-plan"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def humanize_label(value: Any) -> str:
    if value is None:
        return "N/A"
    text_value = str(value).strip()
    replacements = {
        "contracted_procurement": "Contracted Procurement",
        "spot_procurement": "Spot Procurement",
        "hybrid_procurement": "Hybrid Procurement",
        "defer_procurement": "Defer Procurement",
        "no_procurement_required": "No Procurement Required",
        "contracted": "Contracted",
        "spot": "Spot",
    }
    return replacements.get(text_value, text_value.replace("_", " ").title())


def get_procurement_plan(decision: Dict[str, Any]) -> List[Dict[str, Any]]:
    return decision.get("procurement_plan") or decision.get("recommended_procurement_plan") or []


def get_reasoning_items(final_state: Dict[str, Any], strategy: str) -> List[Dict[str, Any]]:
    key = "contracted_reasoning" if strategy == "contracted" else "spot_reasoning"
    reasoning = final_state.get(key) or {}
    return reasoning.get("items") or []


def get_product_level(final_state: Dict[str, Any], strategy: str) -> Dict[str, Any]:
    key = "contracted_reasoning" if strategy == "contracted" else "spot_reasoning"
    reasoning = final_state.get(key) or {}
    return reasoning.get("product_level") or {}


def get_strategy_critical_path(final_state: Dict[str, Any], strategy: str) -> Optional[int]:
    product_level = get_product_level(final_state, strategy)
    value = product_level.get("critical_path_days")

    try:
        return int(value)
    except Exception:
        return None


def build_supplier_intelligence_lookup(final_state: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}

    supplier_intel = final_state.get("supplier_intelligence_output") or {}
    for item in supplier_intel.get("items_analyzed", []) or []:
        item_id = item.get("item_id")
        item_standard_lead_time = (
            item.get("item_standard_lead_time")
            or item.get("item_standard_lead_time_days")
            or item.get("item_lead_time_days")
            or item.get("lead_time_days")
        )

        for supplier in item.get("suppliers", []) or []:
            supplier_name = supplier.get("supplier_name") or supplier.get("name")
            if not item_id or not supplier_name:
                continue

            enriched = dict(supplier)
            enriched["_item_standard_lead_time"] = item_standard_lead_time
            lookup[(str(item_id), str(supplier_name).strip().lower())] = enriched

    return lookup


def find_item_context(final_state: Dict[str, Any], item_id: str) -> Dict[str, Any]:
    supplier_intel = final_state.get("supplier_intelligence_output") or {}
    for item in supplier_intel.get("items_analyzed", []) or []:
        if item.get("item_id") == item_id:
            return item
    return {}


def reasoning_output_to_plan_item(
    reasoning_item: Dict[str, Any],
    strategy: str,
    final_state: Dict[str, Any],
) -> Dict[str, Any]:
    rec = reasoning_item.get("recommended_supplier") or {}
    item_id = reasoning_item.get("item_id")
    item_context = find_item_context(final_state, item_id)

    return {
        "item_id": item_id,
        "item_name": reasoning_item.get("item_name"),
        "strategy": strategy,
        "gross_requirement": reasoning_item.get("gross_requirement"),
        "net_requirement": item_context.get("net_requirement"),
        "current_stock": item_context.get("current_stock"),
        "reserved_qty": item_context.get("reserved_qty"),
        "on_order_qty": item_context.get("on_order_qty"),
        "safety_stock": item_context.get("safety_stock"),
        "selected_supplier_id": rec.get("supplier_id"),
        "selected_supplier_name": rec.get("supplier_name"),
        "order_quantity": rec.get("order_quantity") or rec.get("recommended_order_quantity") or (
            (rec.get("overage_quantity") or 0) + (reasoning_item.get("gross_requirement") or 0)
        ),
        "lead_time_days": rec.get("lead_time_days"),
        "can_deliver_on_time": rec.get("can_deliver_on_time"),
        "risk_level": rec.get("risk_level"),
        "total_cost": rec.get("total_cost"),
        "effective_unit_price": rec.get("effective_unit_price"),
        "overage_quantity": rec.get("overage_quantity"),
        "bulk_discount_applied": rec.get("bulk_discount_applied"),
        "reasoning": rec.get("reasoning"),
        "key_tradeoffs": reasoning_item.get("key_tradeoffs") or [],
        "overall_assessment": reasoning_item.get("overall_assessment"),
        "alternatives_considered": reasoning_item.get("alternatives_considered") or [],
        "source": f"{strategy}_reasoning",
    }


def get_plan_from_strategy(final_state: Dict[str, Any], strategy: str) -> List[Dict[str, Any]]:
    items = get_reasoning_items(final_state, strategy)
    return [
        reasoning_output_to_plan_item(item, strategy=strategy, final_state=final_state)
        for item in items
    ]


def get_supplier_option_for_item(
    final_state: Dict[str, Any],
    item_id: str,
    supplier_name: str,
    strategy: str,
) -> Optional[Dict[str, Any]]:
    lookup = build_supplier_intelligence_lookup(final_state)
    ctx = lookup.get((str(item_id), str(supplier_name).strip().lower()))

    if not ctx:
        return None

    item_context = find_item_context(final_state, item_id)

    if strategy == "spot":
        lead_time = (
            ctx.get("_item_standard_lead_time")
            or ctx.get("item_standard_lead_time")
            or ctx.get("item_standard_lead_time_days")
            or ctx.get("spot_lead_time_days")
        )
        total_cost = (
            ctx.get("total_cost_spot")
            or ctx.get("spot_total_cost")
            or ctx.get("total_spot_cost")
        )
        unit_price = (
            ctx.get("spot_effective_unit_price")
            or ctx.get("effective_unit_price_spot")
            or ctx.get("spot_price")
        )
        bulk_discount = False
    else:
        lead_time = (
            ctx.get("current_lead_time")
            or ctx.get("current_lead_time_days")
            or ctx.get("current_expected_lead_time_days")
            or ctx.get("contracted_lead_time_days")
        )
        total_cost = (
            ctx.get("total_cost_contracted")
            or ctx.get("contracted_total_cost")
            or ctx.get("total_contracted_cost")
        )
        unit_price = (
            ctx.get("effective_unit_price_contracted")
            or ctx.get("contracted_effective_unit_price")
            or ctx.get("contracted_price_after_discount")
            or ctx.get("contracted_price")
        )
        bulk_discount = ctx.get("bulk_discount_applied")

    gross_req = item_context.get("gross_requirement")
    overage = ctx.get("overage_quantity")
    order_qty = ctx.get("recommended_order_quantity")

    return {
        "item_id": item_id,
        "item_name": item_context.get("item_name"),
        "strategy": strategy,
        "gross_requirement": gross_req,
        "net_requirement": item_context.get("net_requirement"),
        "current_stock": item_context.get("current_stock"),
        "reserved_qty": item_context.get("reserved_qty"),
        "on_order_qty": item_context.get("on_order_qty"),
        "safety_stock": item_context.get("safety_stock"),
        "selected_supplier_id": ctx.get("supplier_id"),
        "selected_supplier_name": ctx.get("supplier_name") or supplier_name,
        "order_quantity": order_qty,
        "lead_time_days": lead_time,
        "can_deliver_on_time": None,
        "risk_level": ctx.get("risk_level"),
        "total_cost": total_cost,
        "effective_unit_price": unit_price,
        "overage_quantity": overage,
        "bulk_discount_applied": bulk_discount,
        "reasoning": (
            f"Human selected {ctx.get('supplier_name') or supplier_name} as an override. "
            f"This plan item was rebuilt from precomputed supplier intelligence data using the "
            f"{humanize_label(strategy)} strategy."
        ),
        "key_tradeoffs": [
            "Supplier was selected manually by the reviewer.",
            "AI recommendation remains preserved separately for auditability.",
        ],
        "overall_assessment": "Human override applied.",
        "alternatives_considered": [],
        "source": "human_supplier_override",
    }


def calculate_effective_metrics(plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not plan:
        return {
            "total_procurement_cost": 0.0,
            "critical_path_days": 0,
            "items_in_plan": 0,
        }

    total_cost = 0.0
    critical_path = 0

    for item in plan:
        try:
            total_cost += float(item.get("total_cost") or 0)
        except Exception:
            pass

        try:
            critical_path = max(critical_path, int(item.get("lead_time_days") or 0))
        except Exception:
            pass

    return {
        "total_procurement_cost": round(total_cost, 2),
        "critical_path_days": critical_path,
        "items_in_plan": len(plan),
    }


def apply_strategy_override(
    decision: Dict[str, Any],
    final_state: Dict[str, Any],
    override_strategy: str,
) -> List[Dict[str, Any]]:
    if override_strategy == "no_override":
        return get_procurement_plan(decision)

    if override_strategy == "contracted_procurement":
        return get_plan_from_strategy(final_state, "contracted")

    if override_strategy == "spot_procurement":
        return get_plan_from_strategy(final_state, "spot")

    if override_strategy == "hybrid_procurement":
        return build_hybrid_plan(decision, final_state)

    if override_strategy == "defer_procurement":
        return []

    return get_procurement_plan(decision)


def safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def build_hybrid_plan(decision: Dict[str, Any], final_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Critical-path-aware hybrid strategy.

    Business rule:
    Use the Spot plan's critical path as the earliest achievable production window.
    If a contracted item can arrive within that same window, use contracted pricing.
    If contracted would exceed that window, use spot.

    This avoids paying unnecessary spot premiums while preserving the fastest
    achievable production start date.
    """
    contracted_plan = {item.get("item_id"): item for item in get_plan_from_strategy(final_state, "contracted")}
    spot_plan = {item.get("item_id"): item for item in get_plan_from_strategy(final_state, "spot")}

    spot_critical_path = get_strategy_critical_path(final_state, "spot")

    # Fallback: derive from spot item lead times.
    if spot_critical_path is None:
        spot_critical_path = 0
        for item in spot_plan.values():
            lead_time = safe_int(item.get("lead_time_days")) or 0
            spot_critical_path = max(spot_critical_path, lead_time)

    item_ids = list(dict.fromkeys(list(contracted_plan.keys()) + list(spot_plan.keys())))

    hybrid: List[Dict[str, Any]] = []

    for item_id in item_ids:
        contracted = contracted_plan.get(item_id)
        spot = spot_plan.get(item_id)

        if contracted and not spot:
            chosen = dict(contracted)
            chosen["source"] = "hybrid_contract_only_no_spot_available"
            chosen["hybrid_decision_reason"] = "Only contracted reasoning was available for this item."
            hybrid.append(chosen)
            continue

        if spot and not contracted:
            chosen = dict(spot)
            chosen["source"] = "hybrid_spot_only_no_contract_available"
            chosen["hybrid_decision_reason"] = "Only spot reasoning was available for this item."
            hybrid.append(chosen)
            continue

        if not contracted and not spot:
            continue

        contracted_lead = safe_int(contracted.get("lead_time_days"))
        spot_lead = safe_int(spot.get("lead_time_days"))

        if contracted_lead is not None and contracted_lead <= spot_critical_path:
            chosen = dict(contracted)
            chosen["source"] = "hybrid_contract_within_spot_critical_path"
            chosen["hybrid_decision_reason"] = (
                f"Contracted lead time of {contracted_lead} days is within the spot critical path "
                f"window of {spot_critical_path} days, so contracted pricing is used without delaying "
                f"the earliest achievable production start."
            )
        else:
            chosen = dict(spot)
            chosen["source"] = "hybrid_spot_needed_for_critical_path"
            chosen["hybrid_decision_reason"] = (
                f"Contracted lead time of {contracted_lead} days exceeds the spot critical path "
                f"window of {spot_critical_path} days, so spot procurement is used to avoid delaying "
                f"the earliest achievable production start."
            )

        chosen["hybrid_spot_critical_path_days"] = spot_critical_path
        chosen["hybrid_contract_lead_time_days"] = contracted_lead
        chosen["hybrid_spot_lead_time_days"] = spot_lead
        hybrid.append(chosen)

    return hybrid


def build_effective_procurement_plan(
    decision: Dict[str, Any],
    final_state: Dict[str, Any],
    override_strategy: str = "no_override",
    supplier_overrides: Optional[Dict[str, str]] = None,
    override_reason: Optional[str] = None,
    reviewer: Optional[str] = None,
) -> Dict[str, Any]:
    supplier_overrides = supplier_overrides or {}

    original_strategy = decision.get("recommended_strategy")
    final_strategy = original_strategy if override_strategy == "no_override" else override_strategy

    effective_plan = apply_strategy_override(decision, final_state, override_strategy)

    effective_by_item = {item.get("item_id"): dict(item) for item in effective_plan}

    for item_id, supplier_name in supplier_overrides.items():
        if not supplier_name:
            continue

        current_item = effective_by_item.get(item_id, {})
        strategy = current_item.get("strategy")

        if not strategy:
            if final_strategy == "spot_procurement":
                strategy = "spot"
            else:
                strategy = "contracted"

        replacement = get_supplier_option_for_item(
            final_state=final_state,
            item_id=item_id,
            supplier_name=supplier_name,
            strategy=strategy,
        )

        if replacement:
            replacement["human_override_reason"] = override_reason
            effective_by_item[item_id] = replacement

    final_plan = list(effective_by_item.values())
    metrics = calculate_effective_metrics(final_plan)

    approval_status = "reviewed"
    if override_strategy == "defer_procurement":
        approval_status = "deferred"
    elif override_strategy != "no_override" or supplier_overrides:
        approval_status = "override_applied"

    return {
        "review_layer_version": REVIEW_LAYER_VERSION,
        "created_at": utc_now(),
        "original_ai_recommendation": {
            "recommended_strategy": original_strategy,
            "decision_summary": decision.get("decision_summary"),
            "decision_confidence": decision.get("decision_confidence"),
            "human_review_required": decision.get("human_review_required"),
            "procurement_plan": get_procurement_plan(decision),
        },
        "human_decision": {
            "override_strategy": override_strategy,
            "final_strategy": final_strategy,
            "supplier_overrides": supplier_overrides,
            "override_reason": override_reason,
            "reviewer": reviewer,
            "approval_status": approval_status,
        },
        "effective_plan": final_plan,
        "effective_metrics": metrics,
        "pr_created": False,
        "po_created": False,
    }
