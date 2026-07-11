from __future__ import annotations
from typing import Dict, Any
import streamlit as st
from ui.utils import get_planner_context, humanize_label

def render_planner_context_card(decision: Dict[str, Any]) -> None:
    st.subheader("Planner Reasoning")
    planner = get_planner_context(decision)
    if not planner:
        st.info("Planner context is not available for this workflow run.")
        return
    route = planner.get("selected_route", "N/A")
    complexity_score = planner.get("complexity_score", "N/A")
    complexity_level = planner.get("complexity_level", "N/A")
    route_reason = planner.get("route_reason", "No route reason available.")
    routing_flags = planner.get("routing_flags", {}) or {}
    top_signals = planner.get("top_signals", []) or []
    col1, col2, col3 = st.columns(3)
    col1.metric("Selected Route", humanize_label(route))
    col2.metric("Complexity Level", humanize_label(complexity_level))
    col3.metric("Complexity Score", complexity_score)
    st.markdown("**Why this route was selected**")
    st.write(route_reason)
    if top_signals:
        st.markdown("**Top planner signals**")
        for signal in top_signals[:12]:
            st.write(f"- {signal}")
    with st.expander("Routing flags used by supervisor", expanded=False):
        if routing_flags:
            flag_rows = [{"Flag": key.replace("_", " ").title(), "Value": value} for key, value in routing_flags.items()]
            st.dataframe(flag_rows, width="stretch", hide_index=True)
        else:
            st.write("No routing flags available.")
    with st.expander("Debug: raw planner JSON"):
        st.json(planner)
