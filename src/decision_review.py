"""
Deterministic decision-review layer for ForgeForce Procurement AI.

The module preserves the original AI recommendation as immutable evidence,
applies authorized human strategy and supplier overrides, and produces the
effective procurement plan used for PR creation.

No LLM calls are made here.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.logging import get_logger
from core.observability import traceable_if_enabled


REVIEW_LAYER_VERSION = (
    "decision_review_v3 | production-hardened-critical-path-hybrid"
)

logger = get_logger("decision_review")


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
    return replacements.get(
        text_value,
        text_value.replace("_", " ").title(),
    )


def safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_procurement_plan(
    decision: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return (
        decision.get("procurement_plan")
        or decision.get(
            "recommended_procurement_plan"
        )
        or []
    )


def get_reasoning_items(
    final_state: Dict[str, Any],
    strategy: str,
) -> List[Dict[str, Any]]:
    key = (
        "contracted_reasoning"
        if strategy == "contracted"
        else "spot_reasoning"
    )
    reasoning = final_state.get(key) or {}
    return reasoning.get("items") or []


def get_product_level(
    final_state: Dict[str, Any],
    strategy: str,
) -> Dict[str, Any]:
    key = (
        "contracted_reasoning"
        if strategy == "contracted"
        else "spot_reasoning"
    )
    reasoning = final_state.get(key) or {}
    return reasoning.get("product_level") or {}


def get_strategy_critical_path(
    final_state: Dict[str, Any],
    strategy: str,
) -> Optional[int]:
    return safe_int(
        get_product_level(
            final_state,
            strategy,
        ).get("critical_path_days")
    )


def build_supplier_intelligence_lookup(
    final_state: Dict[str, Any],
) -> Dict[
    Tuple[str, str],
    Dict[str, Any],
]:
    lookup: Dict[
        Tuple[str, str],
        Dict[str, Any],
    ] = {}

    supplier_intelligence = (
        final_state.get(
            "supplier_intelligence_output"
        )
        or {}
    )

    for item in (
        supplier_intelligence.get(
            "items_analyzed",
            [],
        )
        or []
    ):
        item_id = item.get("item_id")
        item_standard_lead_time = (
            item.get(
                "item_standard_lead_time"
            )
            or item.get(
                "item_standard_lead_time_days"
            )
            or item.get(
                "item_lead_time_days"
            )
            or item.get("lead_time_days")
        )

        for supplier in (
            item.get("suppliers", [])
            or []
        ):
            supplier_name = (
                supplier.get("supplier_name")
                or supplier.get("name")
            )

            if not item_id or not supplier_name:
                continue

            enriched = dict(supplier)
            enriched[
                "_item_standard_lead_time"
            ] = item_standard_lead_time

            lookup[
                (
                    str(item_id),
                    str(supplier_name)
                    .strip()
                    .lower(),
                )
            ] = enriched

    return lookup


def build_item_context_lookup(
    final_state: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    supplier_intelligence = (
        final_state.get(
            "supplier_intelligence_output"
        )
        or {}
    )

    return {
        str(item.get("item_id")): item
        for item in (
            supplier_intelligence.get(
                "items_analyzed",
                [],
            )
            or []
        )
        if item.get("item_id")
    }


def find_item_context(
    final_state: Dict[str, Any],
    item_id: str,
) -> Dict[str, Any]:
    return build_item_context_lookup(
        final_state
    ).get(str(item_id), {})


def reasoning_output_to_plan_item(
    reasoning_item: Dict[str, Any],
    strategy: str,
    final_state: Dict[str, Any],
    item_context_lookup: Optional[
        Dict[str, Dict[str, Any]]
    ] = None,
) -> Dict[str, Any]:
    recommendation = (
        reasoning_item.get(
            "recommended_supplier"
        )
        or {}
    )
    item_id = reasoning_item.get("item_id")
    contexts = (
        item_context_lookup
        if item_context_lookup is not None
        else build_item_context_lookup(
            final_state
        )
    )
    item_context = contexts.get(
        str(item_id),
        {},
    )

    gross_requirement = (
        reasoning_item.get(
            "gross_requirement"
        )
        or 0
    )
    order_quantity = (
        recommendation.get("order_quantity")
        or recommendation.get(
            "recommended_order_quantity"
        )
        or (
            (
                recommendation.get(
                    "overage_quantity"
                )
                or 0
            )
            + gross_requirement
        )
    )

    return {
        "item_id": item_id,
        "item_name": reasoning_item.get(
            "item_name"
        ),
        "strategy": strategy,
        "gross_requirement": (
            reasoning_item.get(
                "gross_requirement"
            )
        ),
        "net_requirement": (
            item_context.get(
                "net_requirement"
            )
        ),
        "current_stock": (
            item_context.get(
                "current_stock"
            )
        ),
        "reserved_qty": (
            item_context.get(
                "reserved_qty"
            )
        ),
        "on_order_qty": (
            item_context.get(
                "on_order_qty"
            )
        ),
        "safety_stock": (
            item_context.get(
                "safety_stock"
            )
        ),
        "selected_supplier_id": (
            recommendation.get(
                "supplier_id"
            )
        ),
        "selected_supplier_name": (
            recommendation.get(
                "supplier_name"
            )
        ),
        "order_quantity": order_quantity,
        "lead_time_days": (
            recommendation.get(
                "lead_time_days"
            )
        ),
        "can_deliver_on_time": (
            recommendation.get(
                "can_deliver_on_time"
            )
        ),
        "risk_level": (
            recommendation.get(
                "risk_level"
            )
        ),
        "total_cost": (
            recommendation.get(
                "total_cost"
            )
        ),
        "effective_unit_price": (
            recommendation.get(
                "effective_unit_price"
            )
        ),
        "overage_quantity": (
            recommendation.get(
                "overage_quantity"
            )
        ),
        "bulk_discount_applied": (
            recommendation.get(
                "bulk_discount_applied"
            )
        ),
        "reasoning": (
            recommendation.get(
                "reasoning"
            )
        ),
        "key_tradeoffs": (
            reasoning_item.get(
                "key_tradeoffs"
            )
            or []
        ),
        "overall_assessment": (
            reasoning_item.get(
                "overall_assessment"
            )
        ),
        "alternatives_considered": (
            reasoning_item.get(
                "alternatives_considered"
            )
            or []
        ),
        "source": (
            f"{strategy}_reasoning"
        ),
    }


def get_plan_from_strategy(
    final_state: Dict[str, Any],
    strategy: str,
) -> List[Dict[str, Any]]:
    item_context_lookup = (
        build_item_context_lookup(
            final_state
        )
    )

    return [
        reasoning_output_to_plan_item(
            item,
            strategy=strategy,
            final_state=final_state,
            item_context_lookup=(
                item_context_lookup
            ),
        )
        for item in get_reasoning_items(
            final_state,
            strategy,
        )
    ]


def get_supplier_option_for_item(
    final_state: Dict[str, Any],
    item_id: str,
    supplier_name: str,
    strategy: str,
    *,
    supplier_lookup: Optional[
        Dict[
            Tuple[str, str],
            Dict[str, Any],
        ]
    ] = None,
    item_context_lookup: Optional[
        Dict[str, Dict[str, Any]]
    ] = None,
) -> Optional[Dict[str, Any]]:
    lookup = (
        supplier_lookup
        if supplier_lookup is not None
        else build_supplier_intelligence_lookup(
            final_state
        )
    )
    context = lookup.get(
        (
            str(item_id),
            str(supplier_name)
            .strip()
            .lower(),
        )
    )

    if not context:
        return None

    item_contexts = (
        item_context_lookup
        if item_context_lookup is not None
        else build_item_context_lookup(
            final_state
        )
    )
    item_context = item_contexts.get(
        str(item_id),
        {},
    )

    if strategy == "spot":
        lead_time = (
            context.get(
                "_item_standard_lead_time"
            )
            or context.get(
                "item_standard_lead_time"
            )
            or context.get(
                "item_standard_lead_time_days"
            )
            or context.get(
                "spot_lead_time_days"
            )
        )
        total_cost = (
            context.get("total_cost_spot")
            or context.get(
                "spot_total_cost"
            )
            or context.get(
                "total_spot_cost"
            )
        )
        unit_price = (
            context.get(
                "spot_effective_unit_price"
            )
            or context.get(
                "effective_unit_price_spot"
            )
            or context.get("spot_price")
        )
        bulk_discount = False
    else:
        lead_time = (
            context.get(
                "current_lead_time"
            )
            or context.get(
                "current_lead_time_days"
            )
            or context.get(
                "current_expected_lead_time_days"
            )
            or context.get(
                "contracted_lead_time_days"
            )
        )
        total_cost = (
            context.get(
                "total_cost_contracted"
            )
            or context.get(
                "contracted_total_cost"
            )
            or context.get(
                "total_contracted_cost"
            )
        )
        unit_price = (
            context.get(
                "effective_unit_price_contracted"
            )
            or context.get(
                "contracted_effective_unit_price"
            )
            or context.get(
                "contracted_price_after_discount"
            )
            or context.get(
                "contracted_price"
            )
        )
        bulk_discount = context.get(
            "bulk_discount_applied"
        )

    return {
        "item_id": item_id,
        "item_name": item_context.get(
            "item_name"
        ),
        "strategy": strategy,
        "gross_requirement": (
            item_context.get(
                "gross_requirement"
            )
        ),
        "net_requirement": (
            item_context.get(
                "net_requirement"
            )
        ),
        "current_stock": (
            item_context.get(
                "current_stock"
            )
        ),
        "reserved_qty": (
            item_context.get(
                "reserved_qty"
            )
        ),
        "on_order_qty": (
            item_context.get(
                "on_order_qty"
            )
        ),
        "safety_stock": (
            item_context.get(
                "safety_stock"
            )
        ),
        "selected_supplier_id": (
            context.get("supplier_id")
        ),
        "selected_supplier_name": (
            context.get("supplier_name")
            or supplier_name
        ),
        "order_quantity": (
            context.get(
                "recommended_order_quantity"
            )
        ),
        "lead_time_days": lead_time,
        "can_deliver_on_time": None,
        "risk_level": (
            context.get("risk_level")
        ),
        "total_cost": total_cost,
        "effective_unit_price": (
            unit_price
        ),
        "overage_quantity": (
            context.get(
                "overage_quantity"
            )
        ),
        "bulk_discount_applied": (
            bulk_discount
        ),
        "reasoning": (
            f"Human selected "
            f"{context.get('supplier_name') or supplier_name} "
            "as an override. The item was rebuilt from "
            "precomputed supplier intelligence using the "
            f"{humanize_label(strategy)} strategy."
        ),
        "key_tradeoffs": [
            (
                "Supplier was selected manually "
                "by the reviewer."
            ),
            (
                "The original AI recommendation "
                "remains preserved for auditability."
            ),
        ],
        "overall_assessment": (
            "Human override applied."
        ),
        "alternatives_considered": [],
        "source": (
            "human_supplier_override"
        ),
    }


def calculate_effective_metrics(
    plan: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total_cost = sum(
        safe_float(item.get("total_cost"))
        for item in plan
    )
    critical_path = max(
        (
            safe_int(
                item.get("lead_time_days")
            )
            or 0
            for item in plan
        ),
        default=0,
    )

    return {
        "total_procurement_cost": round(
            total_cost,
            2,
        ),
        "critical_path_days": (
            critical_path
        ),
        "items_in_plan": len(plan),
    }


def apply_strategy_override(
    decision: Dict[str, Any],
    final_state: Dict[str, Any],
    override_strategy: str,
) -> List[Dict[str, Any]]:
    if override_strategy == "no_override":
        return get_procurement_plan(
            decision
        )

    if (
        override_strategy
        == "contracted_procurement"
    ):
        return get_plan_from_strategy(
            final_state,
            "contracted",
        )

    if (
        override_strategy
        == "spot_procurement"
    ):
        return get_plan_from_strategy(
            final_state,
            "spot",
        )

    if (
        override_strategy
        == "hybrid_procurement"
    ):
        return build_hybrid_plan(
            decision,
            final_state,
        )

    if (
        override_strategy
        == "defer_procurement"
    ):
        return []

    logger.warning(
        "decision_review_unknown_strategy_override",
        component="decision_review",
        status="ignored",
        payload={
            "override_strategy": (
                override_strategy
            ),
        },
    )
    return get_procurement_plan(decision)


def build_hybrid_plan(
    decision: Dict[str, Any],
    final_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Use contracted procurement whenever it fits inside the earliest achievable
    spot production window; otherwise use spot to protect the critical path.
    """
    del decision

    contracted_plan = {
        item.get("item_id"): item
        for item in get_plan_from_strategy(
            final_state,
            "contracted",
        )
    }
    spot_plan = {
        item.get("item_id"): item
        for item in get_plan_from_strategy(
            final_state,
            "spot",
        )
    }

    spot_critical_path = (
        get_strategy_critical_path(
            final_state,
            "spot",
        )
    )

    if spot_critical_path is None:
        spot_critical_path = max(
            (
                safe_int(
                    item.get(
                        "lead_time_days"
                    )
                )
                or 0
                for item in (
                    spot_plan.values()
                )
            ),
            default=0,
        )

    item_ids = list(
        dict.fromkeys(
            [
                *contracted_plan.keys(),
                *spot_plan.keys(),
            ]
        )
    )
    hybrid: List[Dict[str, Any]] = []

    for item_id in item_ids:
        contracted = (
            contracted_plan.get(item_id)
        )
        spot = spot_plan.get(item_id)

        if contracted and not spot:
            chosen = dict(contracted)
            chosen["source"] = (
                "hybrid_contract_only_no_spot_available"
            )
            chosen[
                "hybrid_decision_reason"
            ] = (
                "Only contracted reasoning was "
                "available for this item."
            )
            hybrid.append(chosen)
            continue

        if spot and not contracted:
            chosen = dict(spot)
            chosen["source"] = (
                "hybrid_spot_only_no_contract_available"
            )
            chosen[
                "hybrid_decision_reason"
            ] = (
                "Only spot reasoning was "
                "available for this item."
            )
            hybrid.append(chosen)
            continue

        if not contracted or not spot:
            continue

        contracted_lead = safe_int(
            contracted.get(
                "lead_time_days"
            )
        )
        spot_lead = safe_int(
            spot.get("lead_time_days")
        )

        if (
            contracted_lead is not None
            and contracted_lead
            <= spot_critical_path
        ):
            chosen = dict(contracted)
            chosen["source"] = (
                "hybrid_contract_within_spot_critical_path"
            )
            chosen[
                "hybrid_decision_reason"
            ] = (
                f"Contracted lead time of "
                f"{contracted_lead} days is "
                "within the spot critical-path "
                f"window of {spot_critical_path} "
                "days, so contracted pricing is "
                "used without delaying production."
            )
        else:
            chosen = dict(spot)
            chosen["source"] = (
                "hybrid_spot_needed_for_critical_path"
            )
            chosen[
                "hybrid_decision_reason"
            ] = (
                f"Contracted lead time of "
                f"{contracted_lead} days exceeds "
                "the spot critical-path window of "
                f"{spot_critical_path} days, so "
                "spot procurement is used."
            )

        chosen[
            "hybrid_spot_critical_path_days"
        ] = spot_critical_path
        chosen[
            "hybrid_contract_lead_time_days"
        ] = contracted_lead
        chosen[
            "hybrid_spot_lead_time_days"
        ] = spot_lead
        hybrid.append(chosen)

    return hybrid


@traceable_if_enabled(
    name="Build Effective Procurement Decision",
    run_type="chain",
    tags=[
        "decision-review",
        "human-in-the-loop",
        "procurement",
    ],
)
def build_effective_procurement_plan(
    decision: Dict[str, Any],
    final_state: Dict[str, Any],
    override_strategy: str = "no_override",
    supplier_overrides: Optional[
        Dict[str, str]
    ] = None,
    override_reason: Optional[str] = None,
    reviewer: Optional[str] = None,
) -> Dict[str, Any]:
    started_at = time.perf_counter()
    resolved_overrides = {
        str(item_id): str(supplier_name).strip()
        for item_id, supplier_name in (
            supplier_overrides or {}
        ).items()
        if supplier_name
        and str(supplier_name).strip()
    }

    original_strategy = decision.get(
        "recommended_strategy"
    )
    final_strategy = (
        original_strategy
        if override_strategy
        == "no_override"
        else override_strategy
    )

    logger.info(
        "decision_review_started",
        component="decision_review",
        status="running",
        payload={
            "review_layer_version": (
                REVIEW_LAYER_VERSION
            ),
            "original_strategy": (
                original_strategy
            ),
            "requested_strategy_override": (
                override_strategy
            ),
            "supplier_override_count": len(
                resolved_overrides
            ),
            "reviewer_provided": bool(
                reviewer
            ),
        },
    )

    try:
        effective_plan = (
            apply_strategy_override(
                decision,
                final_state,
                override_strategy,
            )
        )
        effective_by_item = {
            str(item.get("item_id")): dict(
                item
            )
            for item in effective_plan
            if item.get("item_id")
        }

        supplier_lookup = (
            build_supplier_intelligence_lookup(
                final_state
            )
        )
        item_context_lookup = (
            build_item_context_lookup(
                final_state
            )
        )
        applied_overrides: Dict[
            str,
            str,
        ] = {}
        rejected_overrides: Dict[
            str,
            str,
        ] = {}

        for (
            item_id,
            supplier_name,
        ) in resolved_overrides.items():
            current_item = (
                effective_by_item.get(
                    item_id,
                    {},
                )
            )
            strategy = current_item.get(
                "strategy"
            )

            if not strategy:
                strategy = (
                    "spot"
                    if final_strategy
                    == "spot_procurement"
                    else "contracted"
                )

            replacement = (
                get_supplier_option_for_item(
                    final_state=final_state,
                    item_id=item_id,
                    supplier_name=(
                        supplier_name
                    ),
                    strategy=strategy,
                    supplier_lookup=(
                        supplier_lookup
                    ),
                    item_context_lookup=(
                        item_context_lookup
                    ),
                )
            )

            if not replacement:
                rejected_overrides[
                    item_id
                ] = supplier_name
                logger.warning(
                    "supplier_override_not_applied",
                    component=(
                        "decision_review"
                    ),
                    status="ignored",
                    payload={
                        "item_id": item_id,
                        "supplier_name": (
                            supplier_name
                        ),
                        "strategy": strategy,
                        "reason": (
                            "supplier_not_found_in_"
                            "precomputed_intelligence"
                        ),
                    },
                )
                continue

            replacement[
                "human_override_reason"
            ] = override_reason
            effective_by_item[
                item_id
            ] = replacement
            applied_overrides[
                item_id
            ] = supplier_name

        final_plan = list(
            effective_by_item.values()
        )
        metrics = (
            calculate_effective_metrics(
                final_plan
            )
        )

        approval_status = "reviewed"
        if (
            override_strategy
            == "defer_procurement"
        ):
            approval_status = "deferred"
        elif (
            override_strategy
            != "no_override"
            or applied_overrides
        ):
            approval_status = (
                "override_applied"
            )

        result = {
            "review_layer_version": (
                REVIEW_LAYER_VERSION
            ),
            "created_at": utc_now(),
            "original_ai_recommendation": {
                "recommended_strategy": (
                    original_strategy
                ),
                "decision_summary": (
                    decision.get(
                        "decision_summary"
                    )
                ),
                "decision_confidence": (
                    decision.get(
                        "decision_confidence"
                    )
                ),
                "human_review_required": (
                    decision.get(
                        "human_review_required"
                    )
                ),
                "procurement_plan": (
                    get_procurement_plan(
                        decision
                    )
                ),
            },
            "human_decision": {
                "override_strategy": (
                    override_strategy
                ),
                "final_strategy": (
                    final_strategy
                ),
                "supplier_overrides": (
                    applied_overrides
                ),
                "rejected_supplier_overrides": (
                    rejected_overrides
                ),
                "override_reason": (
                    override_reason
                ),
                "reviewer": reviewer,
                "approval_status": (
                    approval_status
                ),
            },
            "effective_plan": final_plan,
            "effective_metrics": metrics,
            "pr_created": False,
            "po_created": False,
        }

    except Exception as exc:
        logger.exception(
            "decision_review_failed",
            error=exc,
            component="decision_review",
            status="failed",
            duration_ms=(
                time.perf_counter()
                - started_at
            )
            * 1000,
            payload={
                "original_strategy": (
                    original_strategy
                ),
                "requested_strategy_override": (
                    override_strategy
                ),
                "supplier_override_count": (
                    len(
                        resolved_overrides
                    )
                ),
            },
        )
        raise

    logger.info(
        "decision_review_completed",
        component="decision_review",
        status="success",
        duration_ms=(
            time.perf_counter()
            - started_at
        )
        * 1000,
        payload={
            "original_strategy": (
                original_strategy
            ),
            "final_strategy": (
                final_strategy
            ),
            "approval_status": (
                approval_status
            ),
            "items_in_plan": (
                metrics["items_in_plan"]
            ),
            "total_procurement_cost": (
                metrics[
                    "total_procurement_cost"
                ]
            ),
            "critical_path_days": (
                metrics[
                    "critical_path_days"
                ]
            ),
            "supplier_overrides_requested": (
                len(
                    resolved_overrides
                )
            ),
            "supplier_overrides_applied": (
                len(applied_overrides)
            ),
            "supplier_overrides_rejected": (
                len(rejected_overrides)
            ),
            "has_override_reason": bool(
                override_reason
            ),
        },
    )

    return result
