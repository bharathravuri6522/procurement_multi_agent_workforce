from __future__ import annotations
import streamlit as st
from architecture_explorer.ui_components import node_button, render_arrow

def render(selected: str) -> str:
    st.markdown("#### Conversation Orchestration View")
    st.caption("The Conversation Service coordinates each stage and receives the result before invoking the next one.")
    sequence = [
        ("conversation_service","Conversation Service"),
        ("entity_index","Entity Index"),
        ("query_analyzer","Query Analyzer"),
        ("context_builder","Selective Context Builder"),
        ("answer_generator","Answer Generator"),
        ("summarizer","Conversation Summarizer"),
    ]
    _, center, _ = st.columns([1,1.3,1])
    with center:
        for i,(cid,label) in enumerate(sequence):
            if i: render_arrow("returns to Conversation Service")
            if node_button(cid,label,selected==cid,"conv"): selected=cid
    return selected
