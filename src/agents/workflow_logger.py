"""
workflow_logger_detailed_v1.py
Version: detailed_v1 | full-pricing-risk-routing-debug

Purpose:
- Debug end-to-end procurement workflow behavior.
- Print item-level lead times from demand/supplier intelligence.
- Print supplier-level contracted lead times vs item-level spot lead times.
- Print full pricing evidence:
  * MOQ / batch quantity
  * volume threshold
  * volume discount percentage
  * discount eligibility and shortfall
  * contracted price before/after discount
  * contracted/spot total cost
  * spot-vs-contracted delta
- Print LLM-selected supplier per item with reasoning, tradeoffs, and alternatives.
- Correctly display spot alternative costs from `total_spot_cost`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List


LOGGER_VERSION = "workflow_logger_detailed_v1 | full-pricing-risk-routing-debug"


def _safe(value: Any, default: str = "N/A") -> Any:
    return default if value is None else value


def _line(char: str = "=", width: int = 72) -> None:
    print(char * width)


def _kv(label: str, value: Any, indent: int = 2) -> None:
    print(f"{' ' * indent}{label:<38}: {_safe(value)}")


def _first_available(data: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", "Not available"):
            return value
    return default


def log_header(title: str) -> None:
    _line("=")
    print(title)
    _line("=")
    _kv("Logger Version", LOGGER_VERSION)


def log_node_start(node_name: str) -> None:
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ▶ Entering node: {node_name}")


def log_node_success(node_name: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Completed node: {node_name}")


def log_node_error(node_name: str, error: Exception | str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ Error in node: {node_name}")
    _kv("Error", error)


def log_initial_request(product_id: str, demand_forecast: float, required_date: str) -> None:
    print("\nInitial Request")
    _kv("Product ID", product_id)
    _kv("Demand Forecast", demand_forecast)
    _kv("Required Date", required_date)


def log_demand_analysis(analysis: Dict[str, Any]) -> None:
    """Print demand/inventory output, including item-level constant lead time."""
    print("\nDemand Analysis Summary")
    summary = analysis.get("summary", {}) or {}

    _kv("Product ID", analysis.get("product_id"))
    _kv("BOM Items", summary.get("total_items_in_bom"))
    _kv("Items Requiring Procurement", summary.get("items_requiring_procurement"))
    _kv("Total Net Requirement", summary.get("total_net_requirement_across_items"))
    _kv("Sufficient Inventory", summary.get("has_sufficient_inventory"))

    for item in analysis.get("item_analysis", []) or []:
        inv = item.get("inventory_status", {}) or {}
        print(f"\n  Item: {item.get('item_id')} | {item.get('item_name')}")
        print("  " + "-" * 66)
        _kv("BOM Qty", item.get("bom_quantity"), indent=4)
        _kv("Base Requirement", item.get("base_requirement"), indent=4)
        _kv("Buffer %", item.get("buffer_pct"), indent=4)
        _kv("Buffer Requirement", item.get("buffer_requirement"), indent=4)
        _kv("Gross Requirement", item.get("gross_requirement"), indent=4)
        _kv("Current Stock", inv.get("current_stock"), indent=4)
        _kv("Reserved Qty", inv.get("reserved_qty"), indent=4)
        _kv("On Order Qty", inv.get("on_order_qty"), indent=4)
        _kv("Safety Stock", inv.get("safety_stock"), indent=4)
        _kv("Net Requirement", item.get("net_requirement"), indent=4)
        _kv("Needs Procurement", item.get("needs_procurement"), indent=4)
        _kv("ITEM LEVEL LEAD TIME", inv.get("lead_time_days"), indent=4)


def log_supplier_intelligence(supplier_output: Dict[str, Any]) -> None:
    """Print supplier intelligence context, including pricing calculation evidence."""
    print("\nSupplier Intelligence Summary")
    summary = supplier_output.get("summary", {}) or {}

    _kv("Product ID", supplier_output.get("product_id"))
    _kv("Required Date", supplier_output.get("required_date"))
    _kv("Items Needing Procurement", summary.get("total_items_needing_procurement"))
    _kv("Total Supplier Options", summary.get("total_supplier_options"))
    _kv("Message", summary.get("message"))

    for item_data in supplier_output.get("items_analyzed", []) or []:
        print(f"\n  Item: {item_data.get('item_id')} | {item_data.get('item_name')}")
        print("  " + "-" * 66)
        _kv("Gross Requirement", item_data.get("gross_requirement"), indent=4)
        _kv("Net Requirement", item_data.get("net_requirement"), indent=4)
        _kv("ITEM STANDARD LEAD TIME", item_data.get("item_standard_lead_time_days"), indent=4)
        _kv("Item Unit Cost", item_data.get("item_unit_cost"), indent=4)
        _kv("Item Spot Price Threshold", item_data.get("item_spot_price_threshold"), indent=4)
        suppliers = item_data.get("suppliers", []) or []
        _kv("Suppliers Found", len(suppliers), indent=4)

        for sup in suppliers:
            print(f"\n    Supplier: {sup.get('supplier_name')} ({sup.get('supplier_id')})")
            _kv("Risk Level", sup.get("risk_level"), indent=6)
            _kv("Capacity", sup.get("capacity_status"), indent=6)
            _kv("CONTRACTED LEAD TIME", sup.get("current_lead_time"), indent=6)
            _kv("ITEM/SPOT LEAD TIME", sup.get("item_standard_lead_time_days"), indent=6)
            _kv("On-Time Delivery %", sup.get("on_time_delivery_pct"), indent=6)
            _kv("Quality Rejection %", sup.get("quality_rejection_pct"), indent=6)

            print("      Pricing / Batch Calculation Evidence")
            _kv("MOQ", sup.get("moq"), indent=8)
            _kv("MOQ Used as Batch Size", sup.get("moq_used_as_batch_size"), indent=8)
            _kv("Recommended Order Qty", sup.get("recommended_order_quantity"), indent=8)
            _kv("Overage Qty", sup.get("overage_quantity"), indent=8)

            print("      Contracted Pricing")
            _kv("Contracted Price Raw", sup.get("contracted_price"), indent=8)
            _kv("Contracted Price Before Discount", sup.get("contracted_price_before_discount"), indent=8)
            _kv("Volume Threshold", sup.get("volume_threshold"), indent=8)
            _kv("Volume Discount %", sup.get("volume_discount_pct"), indent=8)
            _kv("Bulk Discount Applied", sup.get("bulk_discount_applied"), indent=8)
            _kv("Bulk Discount Shortfall Qty", sup.get("bulk_discount_shortfall_qty"), indent=8)
            _kv("Bulk Discount Amount", sup.get("bulk_discount_amount"), indent=8)
            _kv("Contracted Price After Discount", sup.get("contracted_price_after_discount"), indent=8)
            _kv("Contracted Total Cost", sup.get("total_cost_contracted"), indent=8)
            _kv("Contracted Effective Unit Price", sup.get("effective_unit_price_contracted"), indent=8)
            _kv("Contracted Overage Cost", sup.get("overage_cost_contracted"), indent=8)

            print("      Spot Pricing")
            _kv("Spot Price Raw", sup.get("spot_price"), indent=8)
            _kv("Spot Price Used", sup.get("spot_price_used"), indent=8)
            _kv("Spot Discount Applied", sup.get("spot_discount_applied"), indent=8)
            _kv("Spot Total Cost", sup.get("total_cost_spot"), indent=8)
            _kv("Spot Effective Unit Price", sup.get("effective_unit_price_spot"), indent=8)
            _kv("Spot Overage Cost", sup.get("overage_cost_spot"), indent=8)
            _kv("Spot vs Contracted Delta", sup.get("spot_vs_contracted_delta"), indent=8)
            _kv("Spot vs Contracted Delta %", sup.get("spot_vs_contracted_delta_pct"), indent=8)


def log_route_planning(route_info: Dict[str, Any]) -> None:
    print("\n" + "-" * 72)
    print("STEP: Supervisor Route Planning")
    print("-" * 72)
    print("\nSupervisor Planning Context")
    for key, value in (route_info or {}).items():
        _kv(key.replace("_", " ").title(), value)


def _get_items(reasoning_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not reasoning_result:
        return []
    items = reasoning_result.get("items", [])
    return items if isinstance(items, list) else []


def log_reasoning_item_recommendations(reasoning_result: Dict[str, Any], strategy_name: str) -> None:
    """Print item-level LLM recommendations and reasoning, including spot alternative costs."""
    is_spot = strategy_name.strip().lower() == "spot"

    print("\n" + "-" * 72)
    print(f"{strategy_name.upper()} ITEM-LEVEL LLM RECOMMENDATIONS")
    print("-" * 72)

    items = _get_items(reasoning_result)
    if not items:
        print("  No item-level LLM recommendation data found.")
        print("  Check whether result.model_dump() is stored under contracted_reasoning/spot_reasoning.")
        return

    for item in items:
        rec = item.get("recommended_supplier", {}) or {}
        print(f"\nItem: {item.get('item_id')} | {item.get('item_name')}")
        print("  " + "-" * 66)
        _kv("Gross Requirement", item.get("gross_requirement"), indent=4)
        _kv("Required Date", item.get("required_date"), indent=4)
        _kv("LLM SELECTED SUPPLIER", rec.get("supplier_name"), indent=4)
        _kv("Supplier ID", rec.get("supplier_id"), indent=4)
        _kv("Lead Time Used By LLM", rec.get("lead_time_days"), indent=4)
        if is_spot:
            _kv("Item Standard Lead Time Used", rec.get("item_standard_lead_time_days"), indent=4)
            _kv("Original Contract Lead Time", rec.get("original_contract_lead_time_days"), indent=4)
        _kv("Can Deliver On Time", rec.get("can_deliver_on_time"), indent=4)
        _kv("Risk Level", rec.get("risk_level"), indent=4)
        _kv("Total Cost", rec.get("total_cost"), indent=4)
        if is_spot:
            _kv("Total Spot Cost", rec.get("total_spot_cost"), indent=4)
            _kv("Spot Unit Price", rec.get("spot_unit_price"), indent=4)
            _kv("Cost Delta vs Contracted", rec.get("cost_delta_vs_contracted"), indent=4)
            _kv("Cost Delta % vs Contracted", rec.get("cost_delta_pct_vs_contracted"), indent=4)
            _kv("Spot Strategy Value", rec.get("spot_strategy_value"), indent=4)
        _kv("Effective Unit Price", rec.get("effective_unit_price"), indent=4)
        _kv("Overage Quantity", rec.get("overage_quantity"), indent=4)
        _kv("Bulk Discount Applied", rec.get("bulk_discount_applied"), indent=4)

        print("\n    LLM REASONING")
        print(f"      {rec.get('reasoning', 'N/A')}")

        tradeoffs = item.get("key_tradeoffs", []) or []
        print("\n    KEY TRADEOFFS CONSIDERED")
        if tradeoffs:
            for idx, tradeoff in enumerate(tradeoffs, start=1):
                print(f"      {idx}. {tradeoff}")
        else:
            print("      N/A")

        print("\n    OVERALL ASSESSMENT")
        print(f"      {item.get('overall_assessment', 'N/A')}")

        alternatives = item.get("alternatives_considered", []) or []
        print("\n    ALTERNATIVES CONSIDERED")
        if alternatives:
            for alt in alternatives:
                print(f"      - {alt.get('supplier_name')}")
                _kv("Why Not Selected", alt.get("why_not_selected"), indent=10)
                alt_cost = _first_available(
                    alt,
                    ["total_cost", "total_spot_cost", "total_contracted_cost", "cost"],
                )
                _kv("Total Cost", alt_cost, indent=10)
                if is_spot:
                    _kv("Spot Total Cost", alt.get("total_spot_cost"), indent=10)
                    _kv("Item Standard Lead Time", alt.get("item_standard_lead_time_days"), indent=10)
                _kv("Risk Level", alt.get("risk_level"), indent=10)
        else:
            print("      N/A")


def log_product_level_summary(reasoning_result: Dict[str, Any], title: str) -> None:
    product_level = (reasoning_result or {}).get("product_level", {}) or {}
    print(f"\n{title}")
    _kv("Critical Path Days", product_level.get("critical_path_days"))
    _kv("Suggested Realistic Date", product_level.get("suggested_realistic_date"))
    _kv("Original Date Feasible", product_level.get("is_original_date_feasible"))
    _kv("Total Procurement Cost", product_level.get("total_procurement_cost"))
    _kv("Total Spot Procurement Cost", product_level.get("total_spot_procurement_cost"))
    _kv("Spot Strategy Assessment", product_level.get("spot_strategy_assessment"))
    _kv("Overall Message", product_level.get("overall_message"))

    chosen = product_level.get("chosen_suppliers_summary", []) or []
    if chosen:
        print("\n  Product-Level Chosen Supplier Summary")
        for row in chosen:
            print(f"    - {row.get('item_id')} | {row.get('item_name')}")
            _kv("Supplier", row.get("supplier_name"), indent=8)
            _kv("Order Quantity", row.get("order_quantity"), indent=8)
            _kv("Lead Time Days", row.get("lead_time_days"), indent=8)
            _kv("Cost", row.get("cost"), indent=8)


def log_reasoning_trace(trace: Iterable[str]) -> None:
    print("\nReasoning Trace")
    for idx, item in enumerate(trace or [], start=1):
        print(f"  {idx}. {item}")


def log_final_summary(final_state: Dict[str, Any]) -> None:
    log_header("WORKFLOW FINAL SUMMARY")
    if final_state.get("risk_complexity_plan"):
        log_risk_complexity_planning(final_state.get("risk_complexity_plan") or {})
    log_product_level_summary(final_state.get("contracted_reasoning") or {}, "Contracted Product-Level Summary")
    if final_state.get("spot_reasoning"):
        log_product_level_summary(final_state.get("spot_reasoning") or {}, "Spot Product-Level Summary")
    if final_state.get("error_message"):
        _kv("Terminal Error", final_state.get("error_message"))
    else:
        print("  ✓ Workflow completed without terminal error.")
    log_reasoning_trace(final_state.get("reasoning_trace", []))
    print(f"  • Final state keys: {list(final_state.keys())}")



def log_risk_complexity_planning(planner_output: Dict[str, Any]) -> None:
    """Print deterministic procurement complexity planner output."""
    print("\n" + "-" * 72)
    print("STEP: Risk / Complexity Planner")
    print("-" * 72)

    _kv("Planner Version", planner_output.get("planner_version"))
    _kv("Required Date", planner_output.get("required_date"))
    _kv("Available Days", planner_output.get("available_days"))
    _kv("Items Needing Procurement", planner_output.get("items_needing_procurement"))
    _kv("Complexity Score", planner_output.get("complexity_score"))
    _kv("Complexity Level", planner_output.get("complexity_level"))
    _kv("Selected Route", planner_output.get("selected_route"))
    _kv("Route Reason", planner_output.get("route_reason"))

    print("\n  Score By Dimension")
    for key, value in (planner_output.get("score_by_dimension") or {}).items():
        _kv(key.replace("_", " ").title(), value, indent=4)

    print("\n  Routing Flags")
    for key, value in (planner_output.get("routing_flags") or {}).items():
        _kv(key.replace("_", " ").title(), value, indent=4)

    print("\n  Item-Level Complexity Breakdown")
    for item in planner_output.get("item_breakdowns", []) or []:
        print(f"\n    Item: {item.get('item_id')} | {item.get('item_name')}")
        _kv("Gross Requirement", item.get("gross_requirement"), indent=6)
        _kv("Net Requirement", item.get("net_requirement"), indent=6)
        _kv("Supplier Count", item.get("supplier_count"), indent=6)
        _kv("Min Contracted Lead Time", item.get("min_contracted_lead_time_days"), indent=6)
        _kv("Item / Spot Lead Time", item.get("min_spot_lead_time_days"), indent=6)
        _kv("Contracted Can Meet Date", item.get("contracted_can_meet_required_date"), indent=6)
        _kv("Spot Can Meet Date", item.get("spot_can_meet_required_date"), indent=6)
        _kv("Average Overage %", item.get("average_overage_pct"), indent=6)
        _kv("Max Overage %", item.get("max_overage_pct"), indent=6)
        _kv("Constrained Supplier Count", item.get("constrained_supplier_count"), indent=6)
        _kv("High Risk Supplier Count", item.get("high_risk_supplier_count"), indent=6)
        _kv("Medium Risk Supplier Count", item.get("medium_risk_supplier_count"), indent=6)
        _kv("Best On-Time Delivery %", item.get("best_on_time_delivery_pct"), indent=6)
        _kv("Worst Quality Rejection %", item.get("worst_quality_rejection_pct"), indent=6)
        _kv("Avg Spot vs Contract Delta %", item.get("avg_spot_vs_contracted_delta_pct"), indent=6)
        signals = item.get("signals") or []
        if signals:
            print("      Signals")
            for signal in signals:
                print(f"        - {signal}")

    top = planner_output.get("top_signals") or []
    if top:
        print("\n  Top Planner Signals")
        for signal in top:
            print(f"    - {signal}")


# ============================================================
# SUPERVISOR EXECUTION STRATEGY / BRANCHING LOGGER
# ============================================================

def log_execution_strategy(plan: Dict[str, Any], nodes_to_run: Iterable[str]) -> None:
    """
    Print the supervisor execution strategy after the risk/complexity planner.

    This is intentionally separate from the detailed pricing logs so we can
    see whether the supervisor is doing:
    - contracted only
    - spot only
    - contracted + spot strategy comparison
    """
    nodes = list(nodes_to_run or [])

    print("\n" + "-" * 72)
    print("STEP: Supervisor Execution Strategy")
    print("-" * 72)
    _kv("Selected Route", plan.get("selected_route"), indent=2)
    _kv("Complexity Score", plan.get("complexity_score"), indent=2)
    _kv("Complexity Level", plan.get("complexity_level"), indent=2)
    _kv("Nodes To Execute", ", ".join(nodes) if nodes else "None", indent=2)

    node_set = set(nodes)
    if node_set == {"contracted_reasoning", "spot_reasoning"}:
        _kv("Execution Mode", "parallel_strategy_comparison", indent=2)
        _kv(
            "Execution Meaning",
            "Contracted and spot strategies are evaluated independently from the same supplier intelligence context.",
            indent=2,
        )
    elif nodes == ["contracted_reasoning"]:
        _kv("Execution Mode", "contracted_only", indent=2)
        _kv("Execution Meaning", "Planner determined contracted reasoning is sufficient.", indent=2)
    elif nodes == ["spot_reasoning"]:
        _kv("Execution Mode", "spot_only", indent=2)
        _kv("Execution Meaning", "Planner determined spot reasoning is the primary strategy.", indent=2)
    else:
        _kv("Execution Mode", "custom_or_unknown", indent=2)

    route_reason = plan.get("route_reason")
    if route_reason:
        _kv("Route Reason", route_reason, indent=2)

    flags = plan.get("routing_flags") or {}
    if flags:
        print("\n  Routing Flags Used For Execution")
        for key, value in flags.items():
            _kv(key.replace("_", " ").title(), value, indent=4)

# ============================================================
# DECISION AGGREGATOR LOGGER
# ============================================================

def log_decision_aggregation(decision: Dict[str, Any]) -> None:
    """Print deterministic decision aggregator output."""
    print("\n" + "-" * 72)
    print("STEP: Decision Aggregator")
    print("-" * 72)

    _kv("Aggregator Version", decision.get("aggregator_version"), indent=2)
    _kv("Product ID", decision.get("product_id"), indent=2)
    _kv("Required Date", decision.get("required_date"), indent=2)
    _kv("Recommended Strategy", decision.get("recommended_strategy"), indent=2)
    _kv("Decision Confidence", decision.get("decision_confidence"), indent=2)
    _kv("Human Review Required", decision.get("human_review_required"), indent=2)
    _kv("Decision Summary", decision.get("decision_summary"), indent=2)

    selected = decision.get("selected_strategy_metrics") or {}
    print("\n  Selected Strategy Metrics")
    _kv("Original Date Feasible", selected.get("is_original_date_feasible"), indent=4)
    _kv("Critical Path Days", selected.get("critical_path_days"), indent=4)
    _kv("Suggested Realistic Date", selected.get("suggested_realistic_date"), indent=4)
    _kv("Total Procurement Cost", selected.get("total_procurement_cost"), indent=4)
    _kv("Items In Plan", selected.get("items_in_plan"), indent=4)

    comparison = decision.get("strategy_comparison") or {}
    contracted = comparison.get("contracted") or {}
    spot = comparison.get("spot") or {}

    print("\n  Strategy Comparison")
    _kv("Contracted Available", contracted.get("available"), indent=4)
    _kv("Contracted Feasible", contracted.get("is_original_date_feasible"), indent=4)
    _kv("Contracted Critical Path", contracted.get("critical_path_days"), indent=4)
    _kv("Contracted Total Cost", contracted.get("total_procurement_cost"), indent=4)
    _kv("Spot Available", spot.get("available"), indent=4)
    _kv("Spot Feasible", spot.get("is_original_date_feasible"), indent=4)
    _kv("Spot Critical Path", spot.get("critical_path_days"), indent=4)
    _kv("Spot Total Cost", spot.get("total_procurement_cost"), indent=4)
    _kv("Cost Delta Spot - Contracted", comparison.get("cost_delta_spot_minus_contracted"), indent=4)
    _kv("Cost Delta % Spot vs Contracted", comparison.get("cost_delta_pct_spot_vs_contracted"), indent=4)
    _kv("Schedule Recovery Days From Spot", comparison.get("schedule_recovery_days_from_spot"), indent=4)

    planner = decision.get("planner_context") or {}
    print("\n  Planner Context Used")
    _kv("Selected Route", planner.get("selected_route"), indent=4)
    _kv("Complexity Score", planner.get("complexity_score"), indent=4)
    _kv("Complexity Level", planner.get("complexity_level"), indent=4)
    _kv("Route Reason", planner.get("route_reason"), indent=4)

    plan = decision.get("procurement_plan") or []
    print("\n  Recommended Procurement Plan")
    if not plan:
        print("    No procurement items selected.")
        return

    for item in plan:
        print(f"\n    Item: {item.get('item_id')} | {item.get('item_name')}")
        _kv("Strategy", item.get("strategy"), indent=6)
        _kv("Gross Requirement", item.get("gross_requirement"), indent=6)
        _kv("Net Requirement", item.get("net_requirement"), indent=6)
        _kv("Selected Supplier", item.get("selected_supplier_name"), indent=6)
        _kv("Supplier ID", item.get("selected_supplier_id"), indent=6)
        _kv("Order Quantity", item.get("order_quantity"), indent=6)
        _kv("Lead Time Days", item.get("lead_time_days"), indent=6)
        _kv("Can Deliver On Time", item.get("can_deliver_on_time"), indent=6)
        _kv("Total Cost", item.get("total_cost"), indent=6)
        _kv("Effective Unit Price", item.get("effective_unit_price"), indent=6)
        _kv("Overage Quantity", item.get("overage_quantity"), indent=6)
        _kv("Bulk Discount Applied", item.get("bulk_discount_applied"), indent=6)

        reasoning = item.get("reasoning")
        if reasoning:
            print("\n      Supplier Reasoning")
            print(f"        {reasoning}")

        tradeoffs = item.get("key_tradeoffs") or []
        if tradeoffs:
            print("\n      Key Tradeoffs")
            for idx, tradeoff in enumerate(tradeoffs, start=1):
                print(f"        {idx}. {tradeoff}")
