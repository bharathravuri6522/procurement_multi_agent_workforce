from __future__ import annotations

import streamlit as st


def render_architecture_explorer_link() -> None:
    """
    Render a link that opens the Streamlit multipage Architecture Explorer in
    a new browser tab.

    The href matches:
        src/pages/Architecture_Explorer.py
    """
    st.markdown(
        """
        <a
            href="/Architecture_Explorer"
            target="_blank"
            rel="noopener noreferrer"
            style="
                display:inline-block;
                padding:0.60rem 0.95rem;
                border:1px solid rgba(120,120,120,.35);
                border-radius:0.55rem;
                text-decoration:none;
                font-weight:650;
                margin-bottom:0.75rem;
            "
        >
            🧭 Open Architecture Explorer
        </a>
        """,
        unsafe_allow_html=True,
    )
