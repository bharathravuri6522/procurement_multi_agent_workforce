"""
Deterministic procurement strategy aggregator.

This module compares already-generated contracted and spot reasoning outputs.
It does not call an LLM and does not recalculate supplier recommendations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.exceptions import DecisionAggregationError
from core.logging import get_logger


AGGREGATOR_VERSION = (
    "decision_aggregator_v3 | production-clean-deterministic"
)

logger = get_logger("decision_aggregator")


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value in (None, "N/A"):
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value in (None, "N/A"):
            return default

        return int(float(value))
    except (TypeError, ValueError):
        return default


def _round_money(value: Any) -> float:
    return round(_safe_float(value), 2)


def _get_product_level(
    strategy_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not strategy_result:
        return {}

    return strategy_result.get("product_level") or {}


def _get_items(
    strategy_result: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not strategy_result:
        return []

    return strategy_result.get("items") or []


def _index_demand_items(
    demand_analysis: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}

    if not demand_analysis:
        return indexed

    for item in (
        demand_analysis.get("item_analysis", []) or []
    ):
        item_id = item.get("item_id")

        if item_id:
            indexed[item_id] = item

    return indexed


def _build_strategy_summary(
    name: str,
    result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    product_level = _get_product_level(result)
    exists = bool(product_level)

    return {
        "strategy": name,
        "available": exists,
        "critical_path_days": (
            _safe_int(
                product_level.get("critical_path_days"),
                0,
            )
            if exists
            else None
        ),
        "suggested_realistic_date": (
            product_level.get("suggested_realistic_date")
            if exists
            else None
        ),
        "is_original_date_feasible": (
            bool(
                product_level.get(
                    "is_original_date_feasible",
                    False,
                )
            )
            if exists
            else False
        ),
        "total_procurement_cost": (
            _round_money(
                product_level.get(
                    "total_procurement_cost"
                )
            )
            if exists
            else None
        ),
        "overall_message": (
            product_level.get("overall_message")
            if exists
            else None
        ),
        "buffer_days": (
            product_level.get("buffer_days")
            if exists
            else None
        ),
        "days_required_with_buffer": (
            product_level.get(
                "days_required_with_buffer"
            )
            if exists
            else None
        ),
        "chosen_suppliers_summary": (
            product_level.get(
                "chosen_suppliers_summary",
                [],
            )
            if exists
            else []
        ),
    }


def _item_procurement_plan(
    selected_strategy: str,
    selected_result: Optional[Dict[str, Any]],
    demand_analysis: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build the execution plan from the selected reasoning output."""
    demand_index = _index_demand_items(
        demand_analysis
    )
    plan: List[Dict[str, Any]] = []

    for item in _get_items(selected_result):
        recommendation = (
            item.get("recommended_supplier") or {}
        )
        item_id = item.get("item_id")
        demand_item = demand_index.get(
            item_id,
            {},
        )
        inventory = (
            demand_item.get("inventory_status") or {}
        )

        order_quantity = recommendation.get(
            "recommended_order_quantity"
        )

        if order_quantity is None:
            order_quantity = (
                _safe_float(
                    item.get("gross_requirement")
                )
                + _safe_float(
                    recommendation.get(
                        "overage_quantity"
                    )
                )
            )

        alternatives = []

        for alternative in (
            item.get(
                "alternatives_considered",
                [],
            )
            or []
        ):
            alternatives.append({
                "supplier_name": (
                    alternative.get("supplier_name")
                ),
                "why_not_selected": (
                    alternative.get(
                        "why_not_selected"
                    )
                ),
                "total_cost": (
                    alternative.get("total_cost")
                ),
                "spot_total_cost": (
                    alternative.get(
                        "total_spot_cost"
                    )
                ),
                "risk_level": (
                    alternative.get("risk_level")
                ),
                "item_standard_lead_time_days": (
                    alternative.get(
                        "item_standard_lead_time_days"
                    )
                ),
            })

        plan.append({
            "item_id": item_id,
            "item_name": item.get("item_name"),
            "strategy": selected_strategy,
            "gross_requirement": item.get(
                "gross_requirement"
            ),
            "net_requirement": demand_item.get(
                "net_requirement"
            ),
            "current_stock": inventory.get(
                "current_stock"
            ),
            "reserved_qty": inventory.get(
                "reserved_qty"
            ),
            "on_order_qty": inventory.get(
                "on_order_qty"
            ),
            "safety_stock": inventory.get(
                "safety_stock"
            ),
            "selected_supplier_id": (
                recommendation.get("supplier_id")
            ),
            "selected_supplier_name": (
                recommendation.get("supplier_name")
            ),
            "order_quantity": order_quantity,
            "lead_time_days": (
                recommendation.get("lead_time_days")
            ),
            "can_deliver_on_time": (
                recommendation.get(
                    "can_deliver_on_time"
                )
            ),
            "risk_level": recommendation.get(
                "risk_level"
            ),
            "total_cost": recommendation.get(
                "total_cost"
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
            "reasoning": recommendation.get(
                "reasoning"
            ),
            "key_tradeoffs": item.get(
                "key_tradeoffs",
                [],
            ),
            "overall_assessment": item.get(
                "overall_assessment"
            ),
            "alternatives_considered": alternatives,
        })

    return plan


def _decision_reason(
    recommended_strategy: str,
    contracted: Dict[str, Any],
    spot: Dict[str, Any],
    route: str,
    cost_delta: Optional[float],
    schedule_recovery_days: Optional[int],
) -> str:
    contracted_available = contracted.get(
        "available"
    )
    spot_available = spot.get("available")
    contracted_feasible = contracted.get(
        "is_original_date_feasible",
        False,
    )
    spot_feasible = spot.get(
        "is_original_date_feasible",
        False,
    )

    if (
        recommended_strategy
        == "contracted_procurement"
        and contracted_available
        and not spot_available
    ):
        return (
            "Contracted procurement is recommended because "
            "the planner determined spot reasoning was not "
            "needed for this request."
        )

    if (
        recommended_strategy
        == "spot_procurement"
        and contracted_available
        and spot_available
        and not contracted_feasible
        and spot_feasible
    ):
        return (
            "Spot procurement is recommended because the "
            "contracted path misses the required date, while "
            "spot procurement meets it. The additional cost is "
            f"{cost_delta}, and the estimated schedule recovery "
            f"is {schedule_recovery_days} day(s)."
        )

    if (
        recommended_strategy
        == "contracted_procurement"
        and contracted_available
        and spot_available
        and contracted_feasible
    ):
        return (
            "Contracted procurement is recommended because it "
            "can meet the required date. Spot procurement does "
            "not provide enough business value to justify the "
            "additional comparison cost/premium."
        )

    if (
        recommended_strategy
        == "spot_procurement"
        and spot_available
        and not contracted_available
    ):
        return (
            "Spot procurement is recommended because spot is "
            "the only available evaluated strategy."
        )

    if (
        recommended_strategy
        == "human_review_required"
    ):
        return (
            "Human review is recommended because neither "
            "evaluated strategy clearly satisfies the business "
            "objective or the risk/cost/timeline trade-off "
            "requires approval."
        )

    return (
        "Recommendation was selected using deterministic "
        f"strategy comparison rules for route '{route}'."
    )


def aggregate_procurement_decision(
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Aggregate prior workflow outputs into one deterministic decision.

    Expected state keys:
    - demand_analysis
    - supplier_intelligence_output
    - risk_complexity_plan
    - contracted_reasoning
    - spot_reasoning, when executed
    """
    if not isinstance(state, dict):
        raise DecisionAggregationError(
            "Workflow state must be a dictionary.",
            component="decision_aggregator",
        )

    demand_analysis = (
        state.get("demand_analysis") or {}
    )
    supplier_output = (
        state.get(
            "supplier_intelligence_output"
        )
        or {}
    )
    planner = (
        state.get("risk_complexity_plan")
        or state.get(
            "procurement_complexity_plan"
        )
        or state.get("route_plan")
        or {}
    )
    contracted_result = state.get(
        "contracted_reasoning"
    )
    spot_result = state.get("spot_reasoning")

    contracted = _build_strategy_summary(
        "contracted",
        contracted_result,
    )
    spot = _build_strategy_summary(
        "spot",
        spot_result,
    )

    contracted_available = contracted["available"]
    spot_available = spot["available"]
    contracted_feasible = contracted[
        "is_original_date_feasible"
    ]
    spot_feasible = spot[
        "is_original_date_feasible"
    ]
    contracted_cost = contracted[
        "total_procurement_cost"
    ]
    spot_cost = spot[
        "total_procurement_cost"
    ]
    contracted_days = contracted[
        "critical_path_days"
    ]
    spot_days = spot[
        "critical_path_days"
    ]

    cost_delta: Optional[float] = None
    cost_delta_pct: Optional[float] = None
    schedule_recovery_days: Optional[int] = None

    if (
        contracted_available
        and spot_available
        and contracted_cost is not None
        and spot_cost is not None
    ):
        cost_delta = round(
            spot_cost - contracted_cost,
            2,
        )
        cost_delta_pct = (
            round(
                (
                    cost_delta
                    / contracted_cost
                )
                * 100,
                2,
            )
            if contracted_cost
            else None
        )

    if (
        contracted_available
        and spot_available
        and contracted_days is not None
        and spot_days is not None
    ):
        schedule_recovery_days = int(
            contracted_days - spot_days
        )

    route = (
        planner.get("selected_route")
        or "unknown"
    )
    complexity_score = planner.get(
        "complexity_score"
    )
    complexity_level = planner.get(
        "complexity_level"
    )

    recommended_strategy = (
        "human_review_required"
    )
    human_review_required = False
    decision_confidence = "medium"

    if (
        contracted_available
        and not spot_available
    ):
        recommended_strategy = (
            "contracted_procurement"
        )
        human_review_required = (
            "risk_review" in route
        )
        decision_confidence = (
            "high"
            if contracted_feasible
            else "medium"
        )

    elif (
        spot_available
        and not contracted_available
    ):
        recommended_strategy = "spot_procurement"
        human_review_required = True
        decision_confidence = "medium"

    elif (
        contracted_available
        and spot_available
    ):
        if (
            not contracted_feasible
            and spot_feasible
        ):
            recommended_strategy = (
                "spot_procurement"
            )
            human_review_required = True
            decision_confidence = "high"

        elif (
            contracted_feasible
            and not spot_feasible
        ):
            recommended_strategy = (
                "contracted_procurement"
            )
            human_review_required = (
                "risk_review" in route
            )
            decision_confidence = "high"

        elif (
            contracted_feasible
            and spot_feasible
        ):
            if (
                cost_delta is not None
                and cost_delta < 0
            ):
                recommended_strategy = (
                    "spot_procurement"
                )
                human_review_required = True
                decision_confidence = "medium"
            else:
                recommended_strategy = (
                    "contracted_procurement"
                )
                human_review_required = (
                    "risk_review" in route
                )
                decision_confidence = "high"

        else:
            if (
                spot_days is not None
                and contracted_days is not None
                and spot_days < contracted_days
            ):
                recommended_strategy = (
                    "spot_procurement"
                )
            else:
                recommended_strategy = (
                    "contracted_procurement"
                )

            human_review_required = True
            decision_confidence = "low"

    if recommended_strategy == "human_review_required":
        selected_result = None
        selected_strategy_label = (
            "human_review_required"
        )
    elif (
        recommended_strategy
        == "contracted_procurement"
    ):
        selected_result = contracted_result
        selected_strategy_label = "contracted"
    else:
        selected_result = spot_result
        selected_strategy_label = "spot"

    procurement_plan = _item_procurement_plan(
        selected_strategy=selected_strategy_label,
        selected_result=selected_result,
        demand_analysis=demand_analysis,
    )

    product_id = (
        supplier_output.get("product_id")
        or demand_analysis.get("product_id")
        or state.get("product_id")
    )
    required_date = (
        supplier_output.get("required_date")
        or demand_analysis.get("required_date")
        or state.get("current_date")
    )

    decision_summary = _decision_reason(
        recommended_strategy=recommended_strategy,
        contracted=contracted,
        spot=spot,
        route=route,
        cost_delta=cost_delta,
        schedule_recovery_days=(
            schedule_recovery_days
        ),
    )

    selected_total_cost = None
    selected_critical_path_days = None
    selected_realistic_date = None
    selected_feasible = False

    if (
        recommended_strategy
        == "contracted_procurement"
    ):
        selected_total_cost = contracted_cost
        selected_critical_path_days = (
            contracted_days
        )
        selected_realistic_date = contracted.get(
            "suggested_realistic_date"
        )
        selected_feasible = (
            contracted_feasible
        )

    elif (
        recommended_strategy
        == "spot_procurement"
    ):
        selected_total_cost = spot_cost
        selected_critical_path_days = spot_days
        selected_realistic_date = spot.get(
            "suggested_realistic_date"
        )
        selected_feasible = spot_feasible

    decision = {
        "aggregator_version": AGGREGATOR_VERSION,
        "generated_at": datetime.now().isoformat(),
        "product_id": product_id,
        "required_date": required_date,
        "recommended_strategy": (
            recommended_strategy
        ),
        "selected_strategy_label": (
            selected_strategy_label
        ),
        "decision_confidence": (
            decision_confidence
        ),
        "human_review_required": (
            human_review_required
        ),
        "decision_summary": decision_summary,
        "selected_strategy_metrics": {
            "is_original_date_feasible": (
                selected_feasible
            ),
            "critical_path_days": (
                selected_critical_path_days
            ),
            "suggested_realistic_date": (
                selected_realistic_date
            ),
            "total_procurement_cost": (
                selected_total_cost
            ),
            "items_in_plan": len(
                procurement_plan
            ),
        },
        "strategy_comparison": {
            "contracted": contracted,
            "spot": spot,
            "cost_delta_spot_minus_contracted": (
                cost_delta
            ),
            "cost_delta_pct_spot_vs_contracted": (
                cost_delta_pct
            ),
            "schedule_recovery_days_from_spot": (
                schedule_recovery_days
            ),
        },
        "planner_context": {
            "selected_route": route,
            "complexity_score": complexity_score,
            "complexity_level": complexity_level,
            "route_reason": planner.get(
                "route_reason"
            ),
            "routing_flags": planner.get(
                "routing_flags",
                {},
            ),
            "top_signals": planner.get(
                "top_signals",
                [],
            ),
        },
        "procurement_plan": procurement_plan,
    }

    logger.info(
        "strategy_decision_selected",
        component="decision_aggregator",
        status="success",
        payload={
            "product_id": product_id,
            "route": route,
            "recommended_strategy": (
                recommended_strategy
            ),
            "decision_confidence": (
                decision_confidence
            ),
            "human_review_required": (
                human_review_required
            ),
            "contracted_available": (
                contracted_available
            ),
            "spot_available": spot_available,
            "contracted_feasible": (
                contracted_feasible
            ),
            "spot_feasible": spot_feasible,
            "contracted_cost": contracted_cost,
            "spot_cost": spot_cost,
            "cost_delta": cost_delta,
            "schedule_recovery_days": (
                schedule_recovery_days
            ),
            "items_in_plan": len(
                procurement_plan
            ),
        },
    )

    if (
        not contracted_available
        and not spot_available
    ):
        logger.warning(
            "no_strategy_outputs_available",
            component="decision_aggregator",
            status="completed_with_warning",
            payload={
                "product_id": product_id,
                "route": route,
            },
        )

    return decision
