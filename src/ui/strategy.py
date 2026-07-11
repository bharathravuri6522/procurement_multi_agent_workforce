from __future__ import annotations
from typing import Dict, Any
import streamlit as st
from ui.utils import get_strategy_summary

def render_strategy_comparison(decision: Dict[str, Any]) -> None:
    st.subheader("Strategy Comparison")
    comparison = decision.get("strategy_comparison", {})
    contracted_summary = get_strategy_summary(comparison, "contracted")
    spot_summary = get_strategy_summary(comparison, "spot")
    table_data = [
        {"Strategy": "Contracted", "Available": contracted_summary.get("available"), "Feasible": contracted_summary.get("feasible"), "Critical Path Days": contracted_summary.get("critical_path_days"), "Total Cost": contracted_summary.get("total_cost")},
        {"Strategy": "Spot", "Available": spot_summary.get("available"), "Feasible": spot_summary.get("feasible"), "Critical Path Days": spot_summary.get("critical_path_days"), "Total Cost": spot_summary.get("total_cost")},
    ]
    st.dataframe(table_data, width="stretch", hide_index=True)
