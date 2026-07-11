from __future__ import annotations

import streamlit as st

from persistence import (
    PERSISTENCE_VERSION,
    get_or_create_app_user,
    list_user_sessions,
    load_latest_review_decision,
    load_latest_workflow_run,
)
from ui.utils import get_decision_from_run, get_final_state_from_run

FORM_PRODUCT_KEY = "procurement_form_product_id"
FORM_BATCH_COUNT_KEY = "procurement_form_batch_count"
FORM_REQUIRED_DATE_KEY = "procurement_form_required_date"
FORM_LOADED_SESSION_KEY = "procurement_form_loaded_session_id"


def init_session_state() -> None:
    defaults = {
        "app_user": None,
        "selected_session": None,
        "latest_run": None,
        "decision_result": None,
        "workflow_final_state": None,
        "last_run_metadata": None,
        "saved_review_decision": None,
        "review_state_run_id": None,
        "review_widgets_initialized_for_run": None,
        FORM_PRODUCT_KEY: None,
        FORM_BATCH_COUNT_KEY: 1,
        FORM_REQUIRED_DATE_KEY: None,
        FORM_LOADED_SESSION_KEY: None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_review_widget_state() -> None:
    keys_to_remove = [
        key for key in st.session_state.keys()
        if key.startswith("review_strategy_")
        or key.startswith("review_reason_")
        or key.startswith("supplier_override_")
    ]
    for key in keys_to_remove:
        del st.session_state[key]

    st.session_state.saved_review_decision = None
    st.session_state.review_state_run_id = None
    st.session_state.review_widgets_initialized_for_run = None


def reset_loaded_session_state(clear_request_form: bool = True) -> None:
    st.session_state.selected_session = None
    st.session_state.latest_run = None
    st.session_state.decision_result = None
    st.session_state.workflow_final_state = None
    st.session_state.last_run_metadata = None
    clear_review_widget_state()

    if clear_request_form:
        st.session_state[FORM_PRODUCT_KEY] = None
        st.session_state[FORM_BATCH_COUNT_KEY] = 1
        st.session_state[FORM_REQUIRED_DATE_KEY] = None
        st.session_state[FORM_LOADED_SESSION_KEY] = None


def load_selected_session(selected_session) -> None:
    clear_review_widget_state()
    st.session_state.selected_session = selected_session

    latest_run = load_latest_workflow_run(selected_session["session_id"])
    st.session_state.latest_run = latest_run
    st.session_state.decision_result = get_decision_from_run(latest_run)
    st.session_state.workflow_final_state = get_final_state_from_run(latest_run)
    st.session_state.last_run_metadata = latest_run

    run_id = latest_run.get("run_id") if latest_run else None
    latest_review = load_latest_review_decision(
        session_id=selected_session["session_id"],
        run_id=run_id,
    )

    st.session_state.saved_review_decision = latest_review
    st.session_state.review_state_run_id = run_id
    st.session_state[FORM_LOADED_SESSION_KEY] = None


def render_sidebar_session_selector() -> None:
    with st.sidebar:
        st.header("Session")
        st.caption(PERSISTENCE_VERSION)

        email = st.text_input("Enter your email", placeholder="name@example.com")
        display_name = st.text_input("Display name", placeholder="Optional")

        if st.button("Continue"):
            try:
                user = get_or_create_app_user(
                    email=email,
                    display_name=display_name or None,
                )
                st.session_state.app_user = user
                reset_loaded_session_state(clear_request_form=True)
                st.success(f"Signed in as {user['email']}")
            except Exception as exc:
                st.error(str(exc))

        if not st.session_state.app_user:
            return

        st.divider()
        user_label = (
            st.session_state.app_user.get("display_name")
            or st.session_state.app_user["email"]
        )
        st.write(f"**User:** {user_label}")

        sessions = list_user_sessions(st.session_state.app_user["app_user_id"])
        session_options = ["Start new session"]
        session_lookup = {}

        for session in sessions:
            label = f"{session['session_id']} | {session.get('title') or 'Untitled'}"
            session_options.append(label)
            session_lookup[label] = session

        selected_label = st.selectbox("Choose session", options=session_options)

        if selected_label == "Start new session":
            if st.button("Prepare New Request", key="prepare_new_request_sidebar"):
                reset_loaded_session_state(clear_request_form=True)
                st.rerun()
            st.info(
                "Configure the product, production batches, and required date in the main request form."
            )
            return

        selected_session = session_lookup[selected_label]
        if st.button("Load Selected Session"):
            load_selected_session(selected_session)
            st.success(f"Loaded session {selected_session['session_id']}")
            st.rerun()
