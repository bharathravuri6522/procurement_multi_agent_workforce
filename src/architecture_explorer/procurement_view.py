from __future__ import annotations
import streamlit as st
from architecture_explorer.ui_components import node_button, render_arrow

def render(selected: str) -> str:
    st.markdown("#### Supervisor-Centered Routing View")
    st.caption("Every specialized node returns an Agent State update. The Supervisor decides the next route.")

    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        if node_button("user_requirement", "User Requirement", selected=="user_requirement", "proc"): selected="user_requirement"
        render_arrow("stored in")
        if node_button("agent_state", "Agent State", selected=="agent_state", "proc"): selected="agent_state"
        render_arrow("read by")
        if node_button("supervisor", "Supervisor Agent", selected=="supervisor", "proc"): selected="supervisor"

    st.markdown("---")
    cols = st.columns(3)
    for col, cid, label in zip(
        cols,
        ["demand_analyst","supplier_intelligence","risk_planner"],
        ["Demand & Inventory Analyst","Supplier Intelligence Agent","Risk & Complexity Planner"],
    ):
        with col:
            st.caption("Supervisor routes to")
            if node_button(cid, label, selected==cid, "proc"): selected=cid
            st.caption("Updates Agent State → returns to Supervisor")

    st.markdown("---")
    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        st.caption("Supervisor delegates selected strategies to")
        if node_button("parallel_executor", "Parallel Strategy Executor", selected=="parallel_executor", "proc"): selected="parallel_executor"

    cols = st.columns(2)
    with cols[0]:
        render_arrow()
        if node_button("contracted_reasoning", "Contracted Reasoning", selected=="contracted_reasoning", "proc"): selected="contracted_reasoning"
    with cols[1]:
        render_arrow()
        if node_button("spot_reasoning", "Spot Reasoning", selected=="spot_reasoning", "proc"): selected="spot_reasoning"

    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        render_arrow("branch results converge")
        if node_button("decision_aggregator", "Decision Aggregator", selected=="decision_aggregator", "proc"): selected="decision_aggregator"
        render_arrow("recommendation presented for")
        if node_button("human_review", "Human Decision Review", selected=="human_review", "proc"): selected="human_review"
    return selected
