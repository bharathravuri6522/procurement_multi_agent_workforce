from __future__ import annotations

import html
import json
from typing import Any, Dict

import streamlit as st


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .arch-hero{padding:1.1rem 1.25rem;border:1px solid rgba(120,120,120,.2);
        border-radius:16px;margin-bottom:1rem;background:linear-gradient(135deg,#f7f8fb,#fff)}
        .arch-kicker{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;
        font-weight:700;opacity:.65}.arch-title{font-size:1.65rem;font-weight:760;margin:.2rem 0}
        .arch-copy{font-size:.98rem;line-height:1.55;opacity:.82}
        .arch-badge{display:inline-block;margin:.15rem .25rem .15rem 0;padding:.28rem .58rem;
        border-radius:999px;background:rgba(95,99,104,.11);font-size:.76rem;font-weight:650}
        .arch-section{margin-top:.85rem;margin-bottom:.35rem;font-size:1.02rem;font-weight:720}
        .arch-note{border-left:4px solid rgba(120,120,120,.45);padding:.72rem .9rem;
        background:rgba(245,247,250,.7);border-radius:0 10px 10px 0}
        .arch-arrow{text-align:center;font-size:1.25rem;opacity:.5;padding:.12rem 0}
        .arch-return{text-align:center;font-size:.76rem;opacity:.66}
        .arch-source{font-family:monospace;font-size:.84rem;background:rgba(120,120,120,.10);
        padding:.65rem .75rem;border-radius:10px}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(title: str, description: str) -> None:
    st.markdown(
        f"""<div class="arch-hero"><div class="arch-kicker">ForgeForce Architecture Explorer</div>
        <div class="arch-title">{html.escape(title)}</div>
        <div class="arch-copy">{html.escape(description)}</div></div>""",
        unsafe_allow_html=True,
    )


def render_arrow(label: str = "") -> None:
    st.markdown('<div class="arch-arrow">↓</div>', unsafe_allow_html=True)
    if label:
        st.markdown(f'<div class="arch-return">{html.escape(label)}</div>', unsafe_allow_html=True)


def node_button(component_id: str, label: str, selected: bool, prefix: str) -> bool:
    return st.button(
        label,
        key=f"{prefix}_{component_id}",
        type="primary" if selected else "secondary",
        width="stretch",
    )


def _section(title: str) -> None:
    st.markdown(f'<div class="arch-section">{html.escape(title)}</div>', unsafe_allow_html=True)


def _list(title: str, values: list[str]) -> None:
    _section(title)
    if not values:
        st.caption("None")
        return
    for value in values:
        st.markdown(f"- {value}")


def render_component_details(component: Dict[str, Any]) -> None:
    st.subheader(component["title"])
    badges = "".join(
        f'<span class="arch-badge">{html.escape(str(value))}</span>'
        for value in component.get("badges", [])
    )
    st.markdown(badges, unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        _section("Purpose")
        st.write(component.get("purpose", ""))
        _section("Why This Stage Is Needed")
        st.write(component.get("why_needed", ""))
    with right:
        _section("Supervisor Routing / Invocation Reason")
        st.markdown(
            f'<div class="arch-note">{html.escape(component.get("routing", ""))}</div>',
            unsafe_allow_html=True,
        )
        _section("Execution Type")
        st.write(component.get("type", ""))

    a, b = st.columns(2)
    with a:
        _list("Reads from Agent State / Workflow Context", component.get("reads_state", []))
    with b:
        _list("Reads from Database / Persistent Data", component.get("reads_database", []))

    _section("Tools and Functions")
    st.dataframe(
        [
            {"Tool / Function": item[0], "Responsibility": item[1]}
            for item in component.get("tools", [])
        ],
        hide_index=True,
        width="stretch",
    )

    _list("Processing Logic", component.get("processing", []))

    a, b = st.columns(2)
    with a:
        _list("Writes to Agent State / Workflow Context", component.get("writes_state", []))
    with b:
        _section("Returns Control To")
        st.write(component.get("returns_to", ""))
        _list("Next Possible Routes", component.get("next_routes", []))

    _section("Output Example")
    st.code(json.dumps(component.get("example", {}), indent=2, default=str), language="json")

    _section("Source")
    st.markdown(
        f'<div class="arch-source">{html.escape(component.get("source", ""))}</div>',
        unsafe_allow_html=True,
    )
