"""
AgentState definition for the Multi-Agent Procurement System.

This TypedDict defines the shared state that flows between all agents
(Supervisor, Demand & Inventory Analyst, Supplier Intelligence, Procurement Executor)
and supports human-in-the-loop + multi-turn follow-up questions.
"""

from typing import TypedDict, List, Optional, Dict, Any, Annotated
from datetime import date
import operator


class AgentState(TypedDict):
    """
    Shared state for the procurement multi-agent system.

    The state is designed to be:
    - Accumulative (messages and reasoning_trace use operator.add)
    - Human-in-the-loop friendly
    - Capable of handling follow-up questions ("Why not SUP-005?")
    - General enough to work for all 6 products
    """

    # ============================================================
    # CORE CONTEXT
    # ============================================================
    product_id: str                          # e.g. "SUP-001", "SUP-002", ..., "SUP-006"
    product_name: Optional[str]              # Human-readable name
    current_date: str                        # ISO format: "2026-07-02"

    # ============================================================
    # DEMAND & INVENTORY ANALYSIS (Agent 2)
    # ============================================================
    demand_forecast: Optional[float]         # Forecasted demand for the period
    current_stock: Optional[float]           # Current available stock
    safety_stock: Optional[float]            # Minimum safety stock level
    net_requirement: Optional[float]         # Calculated: demand - stock + safety
    inventory_analysis: Optional[str]        # Natural language summary from analyst

    # ============================================================
    # SUPPLIER INTELLIGENCE (Agent 3)
    # ============================================================
    supplier_options: Optional[List[Dict[str, Any]]]   # All viable suppliers with details
    recommended_supplier: Optional[Dict[str, Any]]     # Best supplier chosen
    supplier_reasoning: Optional[str]                  # Why this supplier was chosen
    alternative_suppliers: Optional[List[Dict[str, Any]]]  # Other options (for "why not X?")

    # ============================================================
    # HUMAN-IN-THE-LOOP
    # ============================================================
    human_approved: Optional[bool]           # True = approved, False = rejected
    human_feedback: Optional[str]            # Comments from human approver
    final_decision: Optional[str]            # "approved", "rejected", "modified", "pending"

    # ============================================================
    # PROCUREMENT EXECUTION (Agent 4)
    # ============================================================
    pr_created: Optional[bool]
    pr_number: Optional[str]
    po_created: Optional[bool]
    po_number: Optional[str]
    execution_notes: Optional[str]

    # ============================================================
    # MEMORY & REASONING (Critical for follow-up questions)
    # ============================================================
    messages: Annotated[List[Dict[str, Any]], operator.add]
    # List of messages in format: [{"role": "user"|"assistant"|"system", "content": "..."}]

    reasoning_trace: Annotated[List[str], operator.add]
    # Step-by-step reasoning log. Appended by each agent.
    # Example: ["Inventory analyzed: net requirement = 320 units", 
    #           "Supplier Intelligence: SUP-001 recommended due to..."]

    last_user_question: Optional[str]        # Stores the latest follow-up question
    previous_recommendation: Optional[Dict[str, Any]]  # Snapshot of previous recommendation

    # ============================================================
    # CONTROL FLOW (for Supervisor)
    # ============================================================
    next_step: Optional[str]
    # Possible values: 
    # "analyze_inventory", "recommend_supplier", "await_human_approval", 
    # "create_pr", "create_po", "handle_followup", "end"

    current_agent: Optional[str]             # Which agent is currently active
    error_message: Optional[str]             # For error handling / graceful degradation


# ============================================================
# Helper functions (optional but recommended)
# ============================================================

def create_initial_state(
    product_id: str,
    current_date: Optional[str] = None
) -> AgentState:
    """
    Factory function to create a clean initial state for a new procurement run.
    """
    if current_date is None:
        current_date = date.today().isoformat()

    return AgentState(
        product_id=product_id,
        product_name=None,
        current_date=current_date,

        demand_forecast=None,
        current_stock=None,
        safety_stock=None,
        net_requirement=None,
        inventory_analysis=None,

        supplier_options=None,
        recommended_supplier=None,
        supplier_reasoning=None,
        alternative_suppliers=None,

        human_approved=None,
        human_feedback=None,
        final_decision="pending",

        pr_created=False,
        pr_number=None,
        po_created=False,
        po_number=None,
        execution_notes=None,

        messages=[],
        reasoning_trace=[],
        last_user_question=None,
        previous_recommendation=None,

        next_step="analyze_inventory",
        current_agent="Supervisor",
        error_message=None,
    )


def add_reasoning(state: AgentState, reasoning: str) -> AgentState:
    """
    Helper to append reasoning to the trace.
    Usage: state = add_reasoning(state, "Inventory analysis complete")
    """
    if "reasoning_trace" not in state or state["reasoning_trace"] is None:
        state["reasoning_trace"] = []
    state["reasoning_trace"].append(reasoning)
    return state


def add_message(state: AgentState, role: str, content: str) -> AgentState:
    """
    Helper to add a message to the conversation.
    """
    if "messages" not in state or state["messages"] is None:
        state["messages"] = []
    state["messages"].append({"role": role, "content": content})
    return state