from __future__ import annotations
import streamlit as st
from architecture_explorer.ui_components import node_button, render_arrow

def render(selected: str) -> str:
    st.markdown("#### PR → PO Decision Flow")
    st.caption("PR status and existing PO state determine which action is legally allowed.")
    sequence = [
        ("purchase_requisition","Purchase Requisition"),
        ("approval_service","Approval Service"),
        ("execution_supervisor","PR-to-PO Execution Supervisor"),
        ("po_generation","Purchase Order Generation"),
    ]
    _, center, _ = st.columns([1,1.3,1])
    with center:
        for i,(cid,label) in enumerate(sequence):
            if i: render_arrow()
            if node_button(cid,label,selected==cid,"prpo"): selected=cid
    return selected
