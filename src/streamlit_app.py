"""
ForgeForce Procurement AI - Streamlit App

Main Streamlit entry point after splitting the UI into focused modules.

Recommended placement:
    src/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


CURRENT_DIR = Path(__file__).resolve().parent
AGENTS_DIR = CURRENT_DIR / "agents"

if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

if str(AGENTS_DIR) not in sys.path:
    sys.path.append(str(AGENTS_DIR))


from persistence import init_db

try:
    from agents.supervisor import run_procurement_workflow
except Exception:
    from supervisor import run_procurement_workflow

from ui.session import init_session_state, render_sidebar_session_selector
from ui.workflow import render_procurement_request_form
from ui.recommendation import render_decision_summary
from ui.strategy import render_strategy_comparison
from ui.planner import render_planner_context_card
from ui.procurement_plan import render_procurement_plan
from ui.review import render_recommendation_review_controls
from ui.pr_creation import render_pr_creation_panel
from ui.purchase_requisitions import render_purchase_requisitions_page
from ui.purchase_orders import render_purchase_orders_page
from ui.chat import render_chat_panel
from ui.activity import render_activity_log
from core.observability import log_observability_status
from architecture_explorer.app import (
    render_architecture_explorer,
)

st.set_page_config(
    page_title="ForgeForce Procurement AI",
    page_icon="🏭",
    layout="wide",
)

init_session_state()
init_db()
log_observability_status()

render_sidebar_session_selector()

if not st.session_state.app_user:
    st.title("🏭 ForgeForce Procurement AI")
    st.caption(
        "Multi-agent procurement strategy orchestration with session persistence"
    )
    st.info("Enter your email in the sidebar to continue.")
    st.stop()


st.sidebar.markdown("### Application")

app_page = st.sidebar.radio(
    "Navigation",
    [
        "Procurement Analysis",
        "Purchase Requisitions",
        "Purchase Orders",
        "Architecture Explorer",
    ],
    key="main_workflow_navigation",
)


if app_page == "Purchase Requisitions":
    render_purchase_requisitions_page()
    st.stop()


if app_page == "Purchase Orders":
    render_purchase_orders_page()
    st.stop()

if app_page == "Architecture Explorer":
    render_architecture_explorer()
    st.stop()
# ---------------------------------------------------------------------------
# Procurement Analysis Page
# ---------------------------------------------------------------------------

st.title("🏭 ForgeForce Procurement AI")
st.caption(
    "Multi-agent procurement strategy orchestration with session persistence"
)

render_procurement_request_form(run_procurement_workflow)

session = st.session_state.selected_session

if not session:
    st.info("Start a new session or load a previous session from the sidebar.")
    st.stop()

st.divider()
st.caption(f"Active Session: {session['session_id']}")

decision = st.session_state.decision_result
final_state = st.session_state.workflow_final_state

if not decision:
    st.info(
        "This session does not have a saved workflow result yet. "
        "Run a procurement analysis."
    )
    st.stop()

render_decision_summary(decision)
st.divider()

render_strategy_comparison(decision)
st.divider()

render_planner_context_card(decision)
st.divider()

# Pass final_state so the procurement plan UI can enrich alternative supplier
# details from supplier_intelligence_output when decision_aggregation has a
# slimmer schema.
render_procurement_plan(
    decision,
    final_state=final_state,
)
st.divider()

run_id = None
if st.session_state.last_run_metadata:
    run_id = st.session_state.last_run_metadata.get("run_id")

render_recommendation_review_controls(
    decision=decision,
    session_id=session["session_id"],
    run_id=run_id,
    final_state=final_state,
)

st.divider()

# Render the PR preview/creation panel only after the recommendation review.
# The panel loads the saved effective plan, prevents duplicate PR creation for
# the same session/run, and creates the PR with Pending Approval status.
render_pr_creation_panel(session["session_id"])

st.divider()

render_chat_panel(session["session_id"])
render_activity_log(session["session_id"])
