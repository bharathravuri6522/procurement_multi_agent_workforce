from __future__ import annotations

from typing import Any, Dict, List, Optional

from conversation.models import QueryAnalysis


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _supplier_items(final_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (final_state.get("supplier_intelligence_output") or {}).get("items_analyzed") or []


def _reasoning_items(final_state: Dict[str, Any], branch_key: str) -> List[Dict[str, Any]]:
    return (final_state.get(branch_key) or {}).get("items") or []


def find_item_intelligence(final_state: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    return next((i for i in _supplier_items(final_state) if i.get("item_id") == item_id), None)


def find_reasoning_item(final_state: Dict[str, Any], branch_key: str, item_id: str) -> Optional[Dict[str, Any]]:
    return next((i for i in _reasoning_items(final_state, branch_key) if i.get("item_id") == item_id), None)


def find_supplier_record(item: Optional[Dict[str, Any]], supplier_name: str) -> Optional[Dict[str, Any]]:
    if not item:
        return None
    for supplier in item.get("suppliers", []) or []:
        name = supplier.get("supplier_name") or supplier.get("name")
        if _normalize(name) == _normalize(supplier_name):
            return supplier
    return None


def find_supplier_reasoning_position(reasoning_item: Optional[Dict[str, Any]], supplier_name: str) -> Optional[Dict[str, Any]]:
    if not reasoning_item:
        return None
    recommended = reasoning_item.get("recommended_supplier") or {}
    if _normalize(recommended.get("supplier_name")) == _normalize(supplier_name):
        return {
            "role": "recommended_supplier",
            "supplier_record": recommended,
            "detailed_reasoning": recommended.get("reasoning"),
            "overall_assessment": reasoning_item.get("overall_assessment"),
            "key_tradeoffs": reasoning_item.get("key_tradeoffs") or [],
        }
    for alt in reasoning_item.get("alternatives_considered", []) or []:
        if _normalize(alt.get("supplier_name")) == _normalize(supplier_name):
            return {
                "role": "alternative_supplier",
                "supplier_record": alt,
                "why_not_selected": alt.get("why_not_selected") or alt.get("reason") or alt.get("reasoning"),
                "overall_assessment": reasoning_item.get("overall_assessment"),
                "key_tradeoffs": reasoning_item.get("key_tradeoffs") or [],
            }
    return None


def compact_decision_header(input_payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "request": input_payload,
        "recommended_strategy": decision.get("recommended_strategy"),
        "decision_summary": decision.get("decision_summary"),
        "decision_confidence": decision.get("decision_confidence"),
        "selected_strategy_metrics": decision.get("selected_strategy_metrics"),
        "planner_context": decision.get("planner_context") or decision.get("planner_context_used"),
    }


def get_selected_plan_item(decision: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    plan = decision.get("procurement_plan") or decision.get("recommended_procurement_plan") or []
    return next((item for item in plan if item.get("item_id") == item_id), None)


def build_supplier_context(analysis, input_payload, decision, final_state, effective_decision):
    item_id = analysis.item_ids[0]
    intel = find_item_intelligence(final_state, item_id)
    contracted = find_reasoning_item(final_state, "contracted_reasoning", item_id)
    spot = find_reasoning_item(final_state, "spot_reasoning", item_id)
    selected_plan = get_selected_plan_item(decision, item_id)
    selected_name = None
    if selected_plan:
        selected_name = selected_plan.get("selected_supplier_name") or selected_plan.get("selected_supplier")

    names = list(analysis.supplier_names)
    if selected_name and selected_name not in names:
        names.append(selected_name)

    suppliers = {}
    for name in names:
        suppliers[name] = {
            "supplier_intelligence": find_supplier_record(intel, name),
            "contracted_reasoning": find_supplier_reasoning_position(contracted, name),
            "spot_reasoning": find_supplier_reasoning_position(spot, name),
        }

    return {
        "scope": analysis.context_scope,
        "decision_header": compact_decision_header(input_payload, decision),
        "item_context": {k: v for k, v in (intel or {}).items() if k != "suppliers"},
        "selected_plan_item": selected_plan,
        "selected_supplier_name": selected_name,
        "requested_supplier_names": analysis.supplier_names,
        "supplier_records": suppliers,
        "existing_contracted_item_reasoning": contracted,
        "existing_spot_item_reasoning": spot,
        "effective_decision": effective_decision,
    }


def build_supplier_metrics_context(analysis, input_payload, decision, final_state, effective_decision):
    item_id = analysis.item_ids[0]
    supplier_name = analysis.supplier_names[0]
    intel = find_item_intelligence(final_state, item_id)
    supplier = find_supplier_record(intel, supplier_name)
    selected_plan = get_selected_plan_item(decision, item_id)

    metric_fields = [
        "supplier_id", "supplier_name", "contracted_price_usd", "spot_price_usd",
        "contracted_price_before_discount", "contracted_price_after_discount",
        "effective_unit_price", "effective_unit_price_contracted", "effective_unit_price_spot",
        "recommended_order_quantity", "order_quantity", "moq", "volume_threshold",
        "volume_discount_pct", "bulk_discount_applied", "bulk_discount_shortfall_qty",
        "total_cost", "total_cost_contracted", "total_cost_spot", "overage_quantity",
        "current_expected_lead_time_days", "item_standard_lead_time_days",
    ]
    compact = {f: supplier.get(f) for f in metric_fields if supplier and f in supplier}

    return {
        "scope": "supplier_metrics_for_item",
        "decision_header": compact_decision_header(input_payload, decision),
        "item_id": item_id,
        "supplier_name": supplier_name,
        "supplier_metric_fields": compact,
        "full_supplier_record": supplier,
        "selected_plan_item": selected_plan,
        "contracted_reasoning_position": find_supplier_reasoning_position(
            find_reasoning_item(final_state, "contracted_reasoning", item_id), supplier_name
        ),
        "spot_reasoning_position": find_supplier_reasoning_position(
            find_reasoning_item(final_state, "spot_reasoning", item_id), supplier_name
        ),
        "effective_decision": effective_decision,
        "metric_guidance": "Use supplier order quantity, not product demand quantity, when evaluating a volume threshold.",
    }


def build_all_suppliers_context(analysis, input_payload, decision, final_state, effective_decision):
    item_id = analysis.item_ids[0]
    intel = find_item_intelligence(final_state, item_id)
    contracted = find_reasoning_item(final_state, "contracted_reasoning", item_id)
    spot = find_reasoning_item(final_state, "spot_reasoning", item_id)
    selected_plan = get_selected_plan_item(decision, item_id)

    records = []
    for supplier in (intel or {}).get("suppliers", []) or []:
        name = supplier.get("supplier_name") or supplier.get("name")
        records.append({
            "supplier_name": name,
            "supplier_intelligence": supplier,
            "contracted_reasoning": find_supplier_reasoning_position(contracted, name),
            "spot_reasoning": find_supplier_reasoning_position(spot, name),
        })

    return {
        "scope": "all_suppliers_for_item",
        "decision_header": compact_decision_header(input_payload, decision),
        "item_context": {k: v for k, v in (intel or {}).items() if k != "suppliers"},
        "selected_plan_item": selected_plan,
        "supplier_records": records,
        "supplier_count": len(records),
        "existing_contracted_item_reasoning": contracted,
        "existing_spot_item_reasoning": spot,
        "effective_decision": effective_decision,
    }


def build_context_from_analysis(analysis, input_payload, decision, final_state, effective_decision):
    scope = analysis.context_scope
    if scope in {"specific_supplier_for_item", "specific_suppliers_for_item"}:
        return build_supplier_context(analysis, input_payload, decision, final_state, effective_decision)
    if scope == "supplier_metrics_for_item":
        return build_supplier_metrics_context(analysis, input_payload, decision, final_state, effective_decision)
    if scope == "all_suppliers_for_item":
        return build_all_suppliers_context(analysis, input_payload, decision, final_state, effective_decision)

    header = compact_decision_header(input_payload, decision)
    if scope == "specific_item":
        item_id = analysis.item_ids[0]
        return {
            "scope": scope,
            "decision_header": header,
            "item_supplier_intelligence": find_item_intelligence(final_state, item_id),
            "contracted_recommendation": find_reasoning_item(final_state, "contracted_reasoning", item_id),
            "spot_recommendation": find_reasoning_item(final_state, "spot_reasoning", item_id),
            "selected_plan_item": get_selected_plan_item(decision, item_id),
            "effective_decision": effective_decision,
        }
    if scope == "strategy_comparison":
        return {
            "scope": scope,
            "decision_header": header,
            "strategy_comparison": decision.get("strategy_comparison"),
            "contracted_product_level": (final_state.get("contracted_reasoning") or {}).get("product_level"),
            "spot_product_level": (final_state.get("spot_reasoning") or {}).get("product_level"),
            "effective_decision": effective_decision,
        }
    if scope == "effective_plan":
        return {
            "scope": scope,
            "decision_header": header,
            "effective_decision": effective_decision,
            "review_status_message": (
                "If effective_decision is absent, no saved human supplier or strategy override has been recorded."
            ),
        }
    return {
        "scope": "decision_summary",
        "decision_header": header,
        "strategy_comparison": decision.get("strategy_comparison"),
        "procurement_plan": decision.get("procurement_plan") or decision.get("recommended_procurement_plan"),
        "effective_decision": effective_decision,
    }
