"""
supervisor_with_decision_aggregator_v1.py
Version: 1.0-decision-aggregator

Supervisor / Orchestrator for the Multi-Agent Procurement System.

This version keeps the planner-driven routing foundation and adds a deterministic
Decision Aggregator after the strategy reasoning step.

Important design decision:
- The decision aggregator does NOT call an LLM.
- It reads prior outputs from AgentState and combines them into a user-facing
  procurement decision + detailed plan.
"""

from __future__ import annotations

from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from langgraph.graph import StateGraph, END

from agent_state import AgentState
from demand_inventory_analyst import analyze_demand_and_inventory
from supplier_intelligence_agent import recommend_suppliers
from reasoning_node import reason_and_recommend
from spot_reasoning_node import reason_with_spot_strategy
from risk_complexity_planner import calculate_procurement_complexity
from decision_aggregator import aggregate_procurement_decision

from workflow_logger import (
    log_header,
    log_initial_request,
    log_node_start,
    log_node_success,
    log_node_error,
    log_demand_analysis,
    log_supplier_intelligence,
    log_risk_complexity_planning,
    log_execution_strategy,
    log_product_level_summary,
    log_reasoning_item_recommendations,
    log_final_summary,
    log_decision_aggregation,
)


SUPERVISOR_VERSION = "supervisor_with_decision_aggregator_v2 | 1.1-buffer-aware-decision-aggregator"


# ============================================================
# NODE FUNCTIONS
# ============================================================

def demand_analyst_node(state: AgentState) -> Dict[str, Any]:
    node = "demand_analyst"
    log_node_start(node)
    try:
        result = analyze_demand_and_inventory(
            product_id=state["product_id"],
            demand_forecast=state.get("demand_forecast", 0),
            required_date=state.get("current_date"),
        )
        print("  ✓ Demand and inventory analysis generated.")
        log_demand_analysis(result)
        log_node_success(node)
        return {
            "demand_analysis": result,
            "current_agent": node,
            "reasoning_trace": ["Demand & Inventory analysis completed."],
        }
    except Exception as e:
        log_node_error(node, e)
        return {"error_message": str(e)}


def supplier_intelligence_node(state: AgentState) -> Dict[str, Any]:
    node = "supplier_intelligence"
    log_node_start(node)
    if not state.get("demand_analysis"):
        error = "Missing demand_analysis"
        log_node_error(node, error)
        return {"error_message": error}

    try:
        result = recommend_suppliers(state["demand_analysis"])
        print("  ✓ Supplier intelligence context generated.")
        log_supplier_intelligence(result)
        log_node_success(node)
        return {
            "supplier_intelligence_output": result,
            "current_agent": node,
            "reasoning_trace": ["Supplier Intelligence + cost calculations completed."],
        }
    except Exception as e:
        log_node_error(node, e)
        return {"error_message": str(e)}


def _nodes_for_route(selected_route: str) -> List[str]:
    if selected_route in {
        "contracted_then_spot",
        "contracted_then_spot_with_risk_review",
        "parallel_contract_and_spot",
    }:
        return ["contracted_reasoning", "spot_reasoning"]

    if selected_route in {"spot_only", "spot_only_with_risk_review"}:
        return ["spot_reasoning"]

    return ["contracted_reasoning"]


def risk_complexity_planner_node(state: AgentState) -> Dict[str, Any]:
    node = "risk_complexity_planner"
    log_node_start(node)
    if not state.get("supplier_intelligence_output"):
        error = "Missing supplier_intelligence_output"
        log_node_error(node, error)
        return {"error_message": error}

    try:
        plan = calculate_procurement_complexity(state["supplier_intelligence_output"])
        selected_route = plan.get("selected_route", "contracted_only")
        nodes_to_run = _nodes_for_route(selected_route)
        plan["execution_nodes"] = nodes_to_run

        print("  ✓ Risk / complexity plan generated.")
        log_risk_complexity_planning(plan)
        log_execution_strategy(plan, nodes_to_run)
        log_node_success(node)

        return {
            "risk_complexity_plan": plan,
            "next_step": ",".join(nodes_to_run),
            "current_agent": node,
            "reasoning_trace": [
                f"Risk/Complexity Planner selected route '{selected_route}' and execution nodes {nodes_to_run}."
            ],
        }
    except Exception as e:
        log_node_error(node, e)
        return {"error_message": str(e)}


def _run_contracted_reasoning(state: AgentState) -> Dict[str, Any]:
    result = reason_and_recommend(state["supplier_intelligence_output"])
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result
    return result_dict


def _run_spot_reasoning(state: AgentState) -> Dict[str, Any]:
    result = reason_with_spot_strategy(state["supplier_intelligence_output"])
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result
    return result_dict


def strategy_reasoning_executor_node(state: AgentState) -> Dict[str, Any]:
    """
    Execute selected reasoning strategies.

    This node can execute contracted and spot reasoning concurrently using
    ThreadPoolExecutor when the planner requests both. This keeps the graph easy
    to join before Decision Aggregator while still preserving parallel strategy
    evaluation behavior.
    """
    node = "strategy_reasoning_executor"
    log_node_start(node)
    if not state.get("supplier_intelligence_output"):
        error = "Missing supplier_intelligence_output"
        log_node_error(node, error)
        return {"error_message": error}

    next_step = state.get("next_step") or "contracted_reasoning"
    nodes_to_run = [n.strip() for n in str(next_step).split(",") if n.strip()]
    nodes_to_run = [n for n in nodes_to_run if n in {"contracted_reasoning", "spot_reasoning"}]
    if not nodes_to_run:
        nodes_to_run = ["contracted_reasoning"]

    updates: Dict[str, Any] = {
        "current_agent": node,
        "reasoning_trace": [],
    }

    try:
        if len(nodes_to_run) == 1:
            selected = nodes_to_run[0]
            log_node_start(selected)
            if selected == "contracted_reasoning":
                contracted = _run_contracted_reasoning(state)
                print("  ✓ Contracted price reasoning completed.")
                log_product_level_summary(contracted, "Contracted Product-Level Summary")
                log_reasoning_item_recommendations(contracted, "Contracted")
                updates["contracted_reasoning"] = contracted
                updates["reasoning_trace"].append("Contracted Price reasoning completed.")
                log_node_success(selected)
            else:
                spot = _run_spot_reasoning(state)
                print("  ✓ Spot reasoning completed using item-level standard lead time.")
                log_product_level_summary(spot, "Spot Product-Level Summary")
                log_reasoning_item_recommendations(spot, "Spot")
                updates["spot_reasoning"] = spot
                updates["reasoning_trace"].append("Spot Price reasoning completed.")
                log_node_success(selected)

        else:
            # Execute selected strategies in parallel from the same supplier intelligence context.
            futures = {}
            with ThreadPoolExecutor(max_workers=2) as executor:
                for selected in nodes_to_run:
                    log_node_start(selected)
                    if selected == "contracted_reasoning":
                        futures[executor.submit(_run_contracted_reasoning, state)] = selected
                    elif selected == "spot_reasoning":
                        futures[executor.submit(_run_spot_reasoning, state)] = selected

                for future in as_completed(futures):
                    selected = futures[future]
                    result_dict = future.result()
                    if selected == "contracted_reasoning":
                        print("  ✓ Contracted price reasoning completed.")
                        log_product_level_summary(result_dict, "Contracted Product-Level Summary")
                        log_reasoning_item_recommendations(result_dict, "Contracted")
                        updates["contracted_reasoning"] = result_dict
                        updates["reasoning_trace"].append("Contracted Price reasoning completed.")
                    elif selected == "spot_reasoning":
                        print("  ✓ Spot reasoning completed using item-level standard lead time.")
                        log_product_level_summary(result_dict, "Spot Product-Level Summary")
                        log_reasoning_item_recommendations(result_dict, "Spot")
                        updates["spot_reasoning"] = result_dict
                        updates["reasoning_trace"].append("Spot Price reasoning completed.")
                    log_node_success(selected)

        log_node_success(node)
        return updates

    except Exception as e:
        log_node_error(node, e)
        return {"error_message": str(e)}


def decision_aggregator_node(state: AgentState) -> Dict[str, Any]:
    node = "decision_aggregator"
    log_node_start(node)
    try:
        result = aggregate_procurement_decision(state)
        print("  ✓ Decision aggregation completed.")
        log_decision_aggregation(result)
        log_node_success(node)
        return {
            "decision_aggregation": result,
            "previous_recommendation": result,
            "final_decision": "pending_human_review" if result.get("human_review_required") else "recommended",
            "current_agent": node,
            "reasoning_trace": [
                f"Decision Aggregator recommended strategy '{result.get('recommended_strategy')}'."
            ],
        }
    except Exception as e:
        log_node_error(node, e)
        return {"error_message": str(e)}


# ============================================================
# BUILD GRAPH
# ============================================================

def build_supervisor_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("demand_analyst", demand_analyst_node)
    workflow.add_node("supplier_intelligence", supplier_intelligence_node)
    workflow.add_node("risk_complexity_planner", risk_complexity_planner_node)
    workflow.add_node("strategy_reasoning_executor", strategy_reasoning_executor_node)
    workflow.add_node("decision_aggregator", decision_aggregator_node)

    workflow.set_entry_point("demand_analyst")
    workflow.add_edge("demand_analyst", "supplier_intelligence")
    workflow.add_edge("supplier_intelligence", "risk_complexity_planner")
    workflow.add_edge("risk_complexity_planner", "strategy_reasoning_executor")
    workflow.add_edge("strategy_reasoning_executor", "decision_aggregator")
    workflow.add_edge("decision_aggregator", END)

    return workflow.compile()


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def run_procurement_workflow(product_id: str, demand_forecast: float, required_date: str) -> Dict[str, Any]:
    app = build_supervisor_graph()

    initial_state: AgentState = {
        "product_id": product_id,
        "product_name": None,
        "current_date": required_date,
        "demand_forecast": demand_forecast,
        "current_stock": None,
        "safety_stock": None,
        "net_requirement": None,
        "inventory_analysis": None,
        "demand_analysis": None,
        "supplier_options": None,
        "recommended_supplier": None,
        "supplier_reasoning": None,
        "alternative_suppliers": None,
        "supplier_intelligence_output": None,
        "risk_complexity_plan": None,
        "contracted_reasoning": None,
        "spot_reasoning": None,
        "decision_aggregation": None,
        "human_approved": None,
        "human_feedback": None,
        "final_decision": "pending",
        "pr_created": False,
        "pr_number": None,
        "po_created": False,
        "po_number": None,
        "execution_notes": None,
        "messages": [],
        "reasoning_trace": [],
        "last_user_question": None,
        "previous_recommendation": None,
        "next_step": None,
        "current_agent": None,
        "error_message": None,
    }

    return app.invoke(initial_state)


if __name__ == "__main__":
    product_id = "RS-240"
    demand_forecast = 80
    required_date = "2026-07-15"

    log_header("ENTERPRISE PROCUREMENT WORKFLOW")
    print(f"Supervisor Version: {SUPERVISOR_VERSION}")
    log_initial_request(product_id, demand_forecast, required_date)

    final_state = run_procurement_workflow(
        product_id=product_id,
        demand_forecast=demand_forecast,
        required_date=required_date,
    )

    log_final_summary(final_state)
