"""
Supervisor / Orchestrator for the Multi-Agent Procurement System.

This module is responsible for:
- Managing the overall workflow using LangGraph
- Coordinating between specialized agents/nodes
- Making routing decisions (e.g., when to call Spot Price reasoning)
- Maintaining shared state using AgentState
"""

from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END

from agent_state import AgentState
from demand_inventory_analyst import analyze_demand_and_inventory
from supplier_intelligence_agent import recommend_suppliers
from reasoning_node import reason_and_recommend


# ============================================================
# NODE FUNCTIONS
# ============================================================

def demand_analyst_node(state: AgentState) -> Dict[str, Any]:
    """Run demand and inventory analysis."""
    result = analyze_demand_and_inventory(
        product_id=state["product_id"],
        demand_forecast=state.get("demand_forecast", 0),
        required_date=state.get("current_date", "2026-07-15")
    )
    return {
        "demand_analysis": result,
        "current_agent": "demand_analyst",
        "reasoning_trace": ["Demand & Inventory analysis completed."]
    }


def supplier_intelligence_node(state: AgentState) -> Dict[str, Any]:
    """Run supplier intelligence + cost calculations."""
    if not state.get("demand_analysis"):
        return {"error_message": "Missing demand_analysis"}

    result = recommend_suppliers(state["demand_analysis"])
    return {
        "supplier_intelligence_output": result,
        "current_agent": "supplier_intelligence",
        "reasoning_trace": ["Supplier Intelligence + cost calculations completed."]
    }


def contracted_reasoning_node(state: AgentState) -> Dict[str, Any]:
    """Run LLM reasoning on Contracted Price path."""
    if not state.get("supplier_intelligence_output"):
        return {"error_message": "Missing supplier_intelligence_output"}

    result = reason_and_recommend(state["supplier_intelligence_output"])

    # Extract product-level info for routing decision
    product_level = result.product_level if hasattr(result, 'product_level') else {}

    return {
        "contracted_reasoning": result.model_dump() if hasattr(result, 'model_dump') else result,
        "current_agent": "contracted_reasoning",
        "reasoning_trace": ["Contracted Price reasoning completed."],
        "next_step": "spot_reasoning" if not product_level.get("is_original_date_feasible", True) else "end"
    }


def spot_reasoning_node(state: AgentState) -> Dict[str, Any]:
    """Run LLM reasoning on Spot Price path (fallback)."""
    # For now, we reuse the same reasoning node.
    # In future, we can create a dedicated spot_reasoning_node.
    if not state.get("supplier_intelligence_output"):
        return {"error_message": "Missing supplier_intelligence_output"}

    # TODO: In a more advanced version, pass a flag to use Spot logic
    result = reason_and_recommend(state["supplier_intelligence_output"])

    return {
        "spot_reasoning": result.model_dump() if hasattr(result, 'model_dump') else result,
        "current_agent": "spot_reasoning",
        "reasoning_trace": ["Spot Price reasoning completed (fallback)."]
    }


# ============================================================
# ROUTING FUNCTION (Supervisor Decision)
# ============================================================

def should_use_spot(state: AgentState) -> Literal["spot_reasoning", "__end__"]:
    """Decide whether to call Spot reasoning node."""
    next_step = state.get("next_step", "end")
    if next_step == "spot_reasoning":
        return "spot_reasoning"
    return "__end__"


# ============================================================
# BUILD THE GRAPH
# ============================================================

def build_supervisor_graph():
    """Build and compile the procurement workflow graph."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("demand_analyst", demand_analyst_node)
    workflow.add_node("supplier_intelligence", supplier_intelligence_node)
    workflow.add_node("contracted_reasoning", contracted_reasoning_node)
    workflow.add_node("spot_reasoning", spot_reasoning_node)

    # Define flow
    workflow.set_entry_point("demand_analyst")
    workflow.add_edge("demand_analyst", "supplier_intelligence")
    workflow.add_edge("supplier_intelligence", "contracted_reasoning")

    # Conditional routing
    workflow.add_conditional_edges(
        "contracted_reasoning",
        should_use_spot,
        {
            "spot_reasoning": "spot_reasoning",
            "__end__": END
        }
    )

    workflow.add_edge("spot_reasoning", END)

    return workflow.compile()


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def run_procurement_workflow(
    product_id: str,
    demand_forecast: float,
    required_date: str
) -> Dict[str, Any]:
    """
    Main entry point to run the full procurement workflow.
    """
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
        "supplier_options": None,
        "recommended_supplier": None,
        "supplier_reasoning": None,
        "alternative_suppliers": None,
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
        # These will be populated during execution
        "demand_analysis": None,
        "supplier_intelligence_output": None,
        "contracted_reasoning": None,
        "spot_reasoning": None,
    }

    final_state = app.invoke(initial_state)
    return final_state