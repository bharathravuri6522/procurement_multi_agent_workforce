"""
Compact procurement entity indexing for conversational follow-up.

The index resolves item, supplier, and strategy references without placing
full supplier intelligence or reasoning payloads into the query analyzer.
Detailed context is retrieved later by the context builder.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.logging import get_logger
from core.observability import traceable_if_enabled
from persistence import (
    load_workflow_entity_index,
    save_workflow_entity_index,
)


ENTITY_INDEX_VERSION = (
    "procurement_entity_index_v2 | persisted-per-workflow-run"
)

logger = get_logger("conversation.entity_index")

_INDEX_CACHE: Dict[str, Dict[str, Any]] = {}


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _reasoning_items(
    final_state: Dict[str, Any],
    branch_name: str,
) -> List[Dict[str, Any]]:
    branch = final_state.get(branch_name) or {}
    return branch.get("items") or []


def _recommended_supplier_map(
    final_state: Dict[str, Any],
    branch_name: str,
) -> Dict[str, str]:
    recommendations: Dict[str, str] = {}

    for item in _reasoning_items(
        final_state,
        branch_name,
    ):
        item_id = item.get("item_id")
        recommendation = (
            item.get("recommended_supplier") or {}
        )
        supplier_name = recommendation.get(
            "supplier_name"
        )

        if item_id and supplier_name:
            recommendations[item_id] = supplier_name

    return recommendations


def _index_plan_by_item(
    plan: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    return {
        item["item_id"]: item
        for item in plan
        if item.get("item_id")
    }


def _collect_evaluated_suppliers(
    source_item: Dict[str, Any],
    item_id: str,
    supplier_to_items: Dict[str, List[str]],
) -> List[str]:
    evaluated_suppliers: List[str] = []

    for supplier in (
        source_item.get("suppliers", []) or []
    ):
        supplier_name = (
            supplier.get("supplier_name")
            or supplier.get("name")
        )

        if not supplier_name:
            continue

        if supplier_name not in evaluated_suppliers:
            evaluated_suppliers.append(supplier_name)

        linked_items = supplier_to_items.setdefault(
            supplier_name,
            [],
        )

        if item_id not in linked_items:
            linked_items.append(item_id)

    return evaluated_suppliers


def build_procurement_entity_index(
    final_state: Dict[str, Any],
    decision: Dict[str, Any],
    effective_decision: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:
    """
    Build a compact item, supplier, and strategy relationship index.

    Prices, lead times, inventory metrics, and reasoning remain in the saved
    workflow state and are retrieved selectively after query classification.
    """
    final_state = final_state or {}
    decision = decision or {}
    effective_decision = effective_decision or {}

    supplier_output = (
        final_state.get(
            "supplier_intelligence_output"
        )
        or {}
    )
    supplier_items = (
        supplier_output.get("items_analyzed") or []
    )

    contracted_recommendations = (
        _recommended_supplier_map(
            final_state,
            "contracted_reasoning",
        )
    )
    spot_recommendations = (
        _recommended_supplier_map(
            final_state,
            "spot_reasoning",
        )
    )

    decision_plan = (
        decision.get("procurement_plan")
        or decision.get(
            "recommended_procurement_plan"
        )
        or []
    )
    decision_plan_by_item = _index_plan_by_item(
        decision_plan
    )

    effective_plan = (
        effective_decision.get("effective_plan")
        or []
    )
    effective_plan_by_item = _index_plan_by_item(
        effective_plan
    )

    items: List[Dict[str, Any]] = []
    supplier_to_items: Dict[str, List[str]] = {}

    for source_item in supplier_items:
        item_id = source_item.get("item_id")
        item_name = source_item.get("item_name")

        if not item_id:
            logger.warning(
                "entity_index_item_skipped",
                component="conversation_entity_index",
                status="completed_with_warning",
                payload={
                    "reason": "missing_item_id",
                    "item_name": item_name,
                },
            )
            continue

        evaluated_suppliers = (
            _collect_evaluated_suppliers(
                source_item=source_item,
                item_id=item_id,
                supplier_to_items=supplier_to_items,
            )
        )

        decision_item = decision_plan_by_item.get(
            item_id,
            {},
        )
        effective_item = effective_plan_by_item.get(
            item_id,
            {},
        )

        recommended_supplier = (
            decision_item.get(
                "selected_supplier_name"
            )
            or decision_item.get(
                "selected_supplier"
            )
        )

        alternative_suppliers = [
            supplier_name
            for supplier_name in evaluated_suppliers
            if _normalize(supplier_name)
            != _normalize(recommended_supplier)
        ]

        items.append({
            "item_id": item_id,
            "item_name": item_name,
            "recommended_strategy": (
                decision_item.get("strategy")
            ),
            "recommended_supplier": (
                recommended_supplier
            ),
            "contracted_recommended_supplier": (
                contracted_recommendations.get(
                    item_id
                )
            ),
            "spot_recommended_supplier": (
                spot_recommendations.get(item_id)
            ),
            "effective_strategy": (
                effective_item.get("strategy")
            ),
            "effective_supplier": (
                effective_item.get(
                    "selected_supplier_name"
                )
                or effective_item.get(
                    "selected_supplier"
                )
            ),
            "evaluated_suppliers": (
                evaluated_suppliers
            ),
            "alternative_suppliers": (
                alternative_suppliers
            ),
        })

    available_strategies: List[str] = []

    if _reasoning_items(
        final_state,
        "contracted_reasoning",
    ):
        available_strategies.append("contracted")

    if _reasoning_items(
        final_state,
        "spot_reasoning",
    ):
        available_strategies.append("spot")

    if {
        "contracted",
        "spot",
    }.issubset(set(available_strategies)):
        available_strategies.append("hybrid")

    return {
        "entity_index_version": (
            ENTITY_INDEX_VERSION
        ),
        "product_id": (
            decision.get("product_id")
            or supplier_output.get("product_id")
        ),
        "recommended_strategy": (
            decision.get("recommended_strategy")
        ),
        "available_strategies": (
            available_strategies
        ),
        "effective_plan_exists": bool(
            effective_plan
        ),
        "items": items,
        "supplier_to_items": supplier_to_items,
    }


@traceable_if_enabled(
    name="Entity Index Resolution",
    run_type="chain",
    tags=["conversation", "entity-index", "procurement"],
)
def get_or_build_entity_index(
    run_id: str,
    final_state: Dict[str, Any],
    decision: Dict[str, Any],
    effective_decision: Optional[
        Dict[str, Any]
    ] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Return the entity index and the source from which it was obtained.

    Sources:
    - memory_cache
    - persisted_database
    - newly_built_and_persisted
    """
    cached = _INDEX_CACHE.get(run_id)

    if cached is not None:
        return cached, "memory_cache"

    try:
        persisted = load_workflow_entity_index(
            run_id
        )
    except Exception as exc:
        logger.exception(
            "entity_index_load_failed",
            error=exc,
            component="conversation_entity_index",
            status="failed",
            payload={"run_id": run_id},
        )
        raise

    if persisted:
        _INDEX_CACHE[run_id] = persisted
        return persisted, "persisted_database"

    built = build_procurement_entity_index(
        final_state=final_state,
        decision=decision,
        effective_decision=effective_decision,
    )

    try:
        save_workflow_entity_index(
            run_id=run_id,
            entity_index=built,
        )
    except Exception as exc:
        logger.exception(
            "entity_index_save_failed",
            error=exc,
            component="conversation_entity_index",
            status="failed",
            payload={
                "run_id": run_id,
                "item_count": len(
                    built.get("items", [])
                ),
            },
        )
        raise

    _INDEX_CACHE[run_id] = built

    return built, "newly_built_and_persisted"


def invalidate_entity_index(run_id: str) -> None:
    """Remove a workflow-run index from the process-local cache."""
    _INDEX_CACHE.pop(run_id, None)
