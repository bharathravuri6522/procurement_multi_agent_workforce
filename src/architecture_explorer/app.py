from __future__ import annotations

import streamlit as st

from architecture_explorer.architecture_catalog import ARCHITECTURE_CATALOG
from architecture_explorer.conversation_view import render as render_conversation
from architecture_explorer.pr_po_view import render as render_pr_po
from architecture_explorer.procurement_view import render as render_procurement
from architecture_explorer.shared_services_view import render as render_services
from architecture_explorer.ui_components import (
    inject_styles,
    render_component_details,
    render_hero,
)


WORKFLOW_LABELS = {
    "procurement": "Procurement Workflow",
    "conversation": "Conversation Workflow",
    "pr_po": "PR → PO Workflow",
    "services": "Shared Services",
}


def render_architecture_explorer() -> None:
    """
    Render the standalone ForgeForce Architecture Explorer.

    This function does not invoke or modify any production workflow. It only
    renders static architecture metadata and interactive explanatory controls.
    """
    inject_styles()

    if "architecture_workflow" not in st.session_state:
        st.session_state.architecture_workflow = "procurement"

    if "architecture_component" not in st.session_state:
        st.session_state.architecture_component = "supervisor"

    workflow_id = st.segmented_control(
        "Workflow",
        options=list(WORKFLOW_LABELS),
        format_func=lambda value: WORKFLOW_LABELS[value],
        default=st.session_state.architecture_workflow,
        key="architecture_workflow_selector",
    )

    workflow_id = (
        workflow_id
        or st.session_state.architecture_workflow
    )

    if (
        workflow_id
        != st.session_state.architecture_workflow
    ):
        st.session_state.architecture_workflow = (
            workflow_id
        )
        st.session_state.architecture_component = (
            ARCHITECTURE_CATALOG[
                workflow_id
            ]["entry"]
        )

    workflow = ARCHITECTURE_CATALOG[
        workflow_id
    ]
    render_hero(
        workflow["title"],
        workflow["description"],
    )

    selected_component = (
        st.session_state.architecture_component
    )

    if (
        selected_component
        not in workflow["components"]
    ):
        selected_component = workflow["entry"]

    with st.container(border=True):
        if workflow_id == "procurement":
            selected_component = (
                render_procurement(
                    selected_component
                )
            )
        elif workflow_id == "conversation":
            selected_component = (
                render_conversation(
                    selected_component
                )
            )
        elif workflow_id == "pr_po":
            selected_component = render_pr_po(
                selected_component
            )
        else:
            selected_component = (
                render_services(
                    selected_component
                )
            )

    if (
        selected_component
        != st.session_state.architecture_component
    ):
        st.session_state.architecture_component = (
            selected_component
        )
        st.rerun()

    st.markdown("---")
    render_component_details(
        workflow["components"][
            st.session_state.architecture_component
        ]
    )
