from __future__ import annotations
import streamlit as st
from architecture_explorer.ui_components import node_button

def render(selected: str) -> str:
    st.markdown("#### Shared Platform Services")
    st.caption("These support all workflows and are not business-routing nodes.")
    cols = st.columns(3)
    for col,cid,label in zip(
        cols,
        ["persistence","observability","configuration"],
        ["Persistence","LangSmith & Logging","Configuration & Errors"],
    ):
        with col:
            if node_button(cid,label,selected==cid,"svc"): selected=cid
    return selected
