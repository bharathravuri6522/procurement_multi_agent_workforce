from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from persistence import (
    load_workflow_entity_index,
    save_workflow_entity_index,
)


ENTITY_INDEX_VERSION = "procurement_entity_index_v2 | persisted-per-workflow-run"


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _reasoning_items(final_state: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    branch = final_state.get(key) or {}
    return branch.get("items") or []


def _recommended_supplier_map(
    final_state: Dict[str, Any],
    key: str,
) -> Dict[str, str]:
    result: Dict[str, str] = {}

    for item in _reasoning_items(final_state, key):
        item_id = item.get("item_id")
        recommendation = item.get("recommended_supplier") or {}
        supplier_name = recommendation.get("supplier_name")

        if item_id and supplier_name:
            result[item_id] = supplier_name

    return result


def build_procurement_entity_index(
    final_state: Dict[str, Any],
    decision: Dict[str, Any],
    effective_decision: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a compact index containing item/supplier relationships only.

    Detailed prices, lead times, and reasoning remain in final_state and are
    retrieved later by context_builder after query analysis.
    """
    supplier_output = final_state.get("supplier_intelligence_output") or {}
    supplier_items = supplier_output.get("items_analyzed") or []

    contracted_map = _recommended_supplier_map(
        final_state, "contracted_reasoning"
    )
    spot_map = _recommended_supplier_map(
        final_state, "spot_reasoning"
    )

    decision_plan = (
        decision.get("procurement_plan")
        or decision.get("recommended_procurement_plan")
        or []
    )
    decision_plan_map = {
        item.get("item_id"): item
        for item in decision_plan
        if item.get("item_id")
    }

    effective_plan = (
        effective_decision.get("effective_plan", [])
        if effective_decision
        else []
    )
    effective_plan_map = {
        item.get("item_id"): item
        for item in effective_plan
        if item.get("item_id")
    }

    items: List[Dict[str, Any]] = []
    supplier_to_items: Dict[str, List[str]] = {}

    for source_item in supplier_items:
        item_id = source_item.get("item_id")
        item_name = source_item.get("item_name")

        if not item_id:
            continue

        evaluated_suppliers: List[str] = []

        for supplier in source_item.get("suppliers", []) or []:
            supplier_name = (
                supplier.get("supplier_name")
                or supplier.get("name")
            )

            if not supplier_name:
                continue

            if supplier_name not in evaluated_suppliers:
                evaluated_suppliers.append(supplier_name)

            supplier_to_items.setdefault(supplier_name, [])
            if item_id not in supplier_to_items[supplier_name]:
                supplier_to_items[supplier_name].append(item_id)

        decision_item = decision_plan_map.get(item_id, {})
        effective_item = effective_plan_map.get(item_id, {})

        recommended_supplier = (
            decision_item.get("selected_supplier_name")
            or decision_item.get("selected_supplier")
        )

        alternatives = [
            supplier_name
            for supplier_name in evaluated_suppliers
            if _normalize(supplier_name) != _normalize(recommended_supplier)
        ]

        items.append({
            "item_id": item_id,
            "item_name": item_name,
            "recommended_strategy": decision_item.get("strategy"),
            "recommended_supplier": recommended_supplier,
            "contracted_recommended_supplier": contracted_map.get(item_id),
            "spot_recommended_supplier": spot_map.get(item_id),
            "effective_strategy": effective_item.get("strategy"),
            "effective_supplier": (
                effective_item.get("selected_supplier_name")
                or effective_item.get("selected_supplier")
            ),
            "evaluated_suppliers": evaluated_suppliers,
            "alternative_suppliers": alternatives,
        })

    available_strategies: List[str] = []

    if _reasoning_items(final_state, "contracted_reasoning"):
        available_strategies.append("contracted")

    if _reasoning_items(final_state, "spot_reasoning"):
        available_strategies.append("spot")

    if {"contracted", "spot"}.issubset(set(available_strategies)):
        available_strategies.append("hybrid")

    return {
        "entity_index_version": ENTITY_INDEX_VERSION,
        "product_id": (
            decision.get("product_id")
            or supplier_output.get("product_id")
        ),
        "recommended_strategy": decision.get("recommended_strategy"),
        "available_strategies": available_strategies,
        "effective_plan_exists": bool(effective_plan),
        "items": items,
        "supplier_to_items": supplier_to_items,
    }


_INDEX_CACHE: Dict[str, Dict[str, Any]] = {}


def get_or_build_entity_index(
    run_id: str,
    final_state: Dict[str, Any],
    decision: Dict[str, Any],
    effective_decision: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Return:
        (entity_index, source)

    source is one of:
        memory_cache
        persisted_database
        newly_built_and_persisted
    """
    if run_id in _INDEX_CACHE:
        return _INDEX_CACHE[run_id], "memory_cache"

    persisted = load_workflow_entity_index(run_id)

    if persisted:
        _INDEX_CACHE[run_id] = persisted
        return persisted, "persisted_database"

    built = build_procurement_entity_index(
        final_state=final_state,
        decision=decision,
        effective_decision=effective_decision,
    )

    save_workflow_entity_index(
        run_id=run_id,
        entity_index=built,
    )

    _INDEX_CACHE[run_id] = built
    return built, "newly_built_and_persisted"


def invalidate_entity_index(run_id: str) -> None:
    _INDEX_CACHE.pop(run_id, None)
