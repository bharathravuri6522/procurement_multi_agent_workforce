from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from persistence import (
    load_messages,
    load_latest_conversation_summary,
)

from conversation_service import handle_followup_message


DEFAULT_VISIBLE_MESSAGES = 10   # 5 user/assistant turns
LOAD_MORE_MESSAGES = 10         # Load 5 additional turns per click
MAX_HISTORY_MESSAGES = 500      # UI safety cap


def _history_state_key(session_id: str) -> str:
    return f"conversation_visible_message_count_{session_id}"


def _normalize_message_order(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Display messages from oldest to newest."""
    return sorted(
        messages,
        key=lambda message: str(message.get("created_at") or ""),
    )


def render_conversation_summary(session_id: str) -> None:
    latest_summary = load_latest_conversation_summary(session_id)

    if not latest_summary:
        return

    summary_text = latest_summary.get("summary_text")

    if not summary_text:
        return

    with st.expander("Conversation Memory Summary", expanded=False):
        st.write(summary_text)

        messages_covered = latest_summary.get("messages_covered")
        if messages_covered is not None:
            st.caption(f"Messages summarized: {messages_covered}")


def load_visible_conversation_messages(
    session_id: str,
    visible_count: int,
) -> List[Dict[str, Any]]:
    safe_limit = max(
        DEFAULT_VISIBLE_MESSAGES,
        min(visible_count, MAX_HISTORY_MESSAGES),
    )

    messages = load_messages(
        session_id,
        limit=safe_limit,
    )

    return _normalize_message_order(messages)


def render_chat_messages(
    session_id: str,
    visible_count: int,
) -> int:
    messages = load_visible_conversation_messages(
        session_id=session_id,
        visible_count=visible_count,
    )

    if not messages:
        st.info("No conversation messages yet.")
        return 0

    for message in messages:
        role = message.get("role", "assistant")

        if role not in {"user", "assistant"}:
            role = "assistant"

        with st.chat_message(role):
            st.write(message.get("content", ""))

    return len(messages)


def render_history_controls(
    session_id: str,
    visible_count: int,
    loaded_count: int,
) -> None:
    """
    Show controls for loading older stored messages.

    Because persistence currently provides a limit-based API without a total
    count, matching the requested limit means older messages may still exist.
    """
    possible_older_messages = (
        loaded_count >= visible_count
        and visible_count < MAX_HISTORY_MESSAGES
    )

    col1, col2, col3 = st.columns([1.4, 1.1, 3])

    with col1:
        if possible_older_messages:
            if st.button(
                "Load previous messages",
                key=f"load_previous_messages_{session_id}",
                use_container_width=True,
            ):
                st.session_state[_history_state_key(session_id)] = min(
                    visible_count + LOAD_MORE_MESSAGES,
                    MAX_HISTORY_MESSAGES,
                )
                st.rerun()

    with col2:
        if visible_count > DEFAULT_VISIBLE_MESSAGES:
            if st.button(
                "Show latest only",
                key=f"show_latest_messages_{session_id}",
                use_container_width=True,
            ):
                st.session_state[_history_state_key(session_id)] = (
                    DEFAULT_VISIBLE_MESSAGES
                )
                st.rerun()

    with col3:
        turns_shown = loaded_count // 2
        st.caption(
            f"Showing {loaded_count} messages "
            f"(about {turns_shown} conversation turns)."
        )


def render_chat_panel(session_id: str) -> None:
    """
    Show the latest five turns by default and progressively load older history.
    """
    st.subheader("Session Conversation")

    st.caption(
        "Ask follow-up questions about the saved procurement recommendation, "
        "suppliers, alternatives, strategy, cost, lead time, risk, inventory, "
        "or the reviewed effective plan."
    )

    render_conversation_summary(session_id)

    state_key = _history_state_key(session_id)

    if state_key not in st.session_state:
        st.session_state[state_key] = DEFAULT_VISIBLE_MESSAGES

    visible_count = int(st.session_state[state_key])

    loaded_count = render_chat_messages(
        session_id=session_id,
        visible_count=visible_count,
    )

    render_history_controls(
        session_id=session_id,
        visible_count=visible_count,
        loaded_count=loaded_count,
    )

    user_question = st.chat_input(
        "Ask a follow-up about this procurement recommendation..."
    )

    if not user_question:
        return

    try:
        with st.spinner(
            "Analyzing your question and retrieving relevant procurement context..."
        ):
            handle_followup_message(
                session_id=session_id,
                user_question=user_question,
            )

        # Keep the panel compact after each new answer.
        st.session_state[state_key] = DEFAULT_VISIBLE_MESSAGES
        st.rerun()

    except Exception as exc:
        st.error(f"Unable to answer the follow-up question: {exc}")
