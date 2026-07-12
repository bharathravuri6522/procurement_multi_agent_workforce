from __future__ import annotations
import streamlit as st
from persistence import load_session_activity

def render_activity_log(session_id: str) -> None:
    with st.expander("Activity Log"):
        activities = load_session_activity(session_id, limit=20)
        if not activities:
            st.write("No activity logged yet.")
            return
        st.dataframe(activities, width="stretch", hide_index=True)
