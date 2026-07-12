from __future__ import annotations
from typing import Dict, Any
import streamlit as st
from ui.utils import format_money, format_pct, format_optional_days, humanize_label

def render_metric_row(decision: Dict[str, Any]) -> None:
    selected = decision.get("selected_strategy_metrics", {})
    comparison = decision.get("strategy_comparison", {})
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Recommended Strategy", humanize_label(decision.get("recommended_strategy", "N/A")))
    col2.metric("Confidence", humanize_label(decision.get("decision_confidence", "N/A")))
    col3.metric("Critical Path", format_optional_days(selected.get("critical_path_days")))
    col4.metric("Total Cost", format_money(selected.get("total_procurement_cost")))
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Suggested Date", selected.get("suggested_realistic_date", "N/A"))
    col6.metric("Spot Premium", format_money(comparison.get("cost_delta_spot_minus_contracted")))
    col7.metric("Spot Premium %", format_pct(comparison.get("cost_delta_pct_spot_vs_contracted")))
    col8.metric("Schedule Recovery", format_optional_days(comparison.get("schedule_recovery_days_from_spot")))

def render_decision_summary(decision: Dict[str, Any]) -> None:
    st.subheader("Executive Decision Summary")
    recommendation = decision.get("recommended_strategy", "N/A")
    confidence = decision.get("decision_confidence", "N/A")
    human_review = decision.get("human_review_required", False)
    if recommendation == "spot_procurement":
        st.warning(f"Recommended Strategy: **{humanize_label(recommendation)}**")
    elif recommendation in {"contracted_procurement", "no_procurement_required"}:
        st.success(f"Recommended Strategy: **{humanize_label(recommendation)}**")
    else:
        st.info(f"Recommended Strategy: **{humanize_label(recommendation)}**")
    st.write(decision.get("decision_summary", "No decision summary available."))
    cols = st.columns(2)
    cols[0].write(f"**Decision Confidence:** {humanize_label(confidence)}")
    cols[1].write(f"**Human Review Required:** {'Yes' if human_review else 'No'}")
    render_metric_row(decision)
