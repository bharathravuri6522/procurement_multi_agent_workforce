from __future__ import annotations
import json
from typing import Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from persistence import load_messages, load_latest_conversation_summary, save_conversation_summary

DEFAULT_SUMMARY_MODEL = "gpt-4o-mini"
SUMMARY_TRIGGER_MESSAGE_COUNT = 8

def _dump(value: Any, max_chars: int = 16000) -> str:
    text = json.dumps(value, indent=2, default=str)
    return text if len(text) <= max_chars else text[:max_chars] + "\n...TRUNCATED..."

def should_summarize_conversation(session_id: str, trigger_message_count: int = SUMMARY_TRIGGER_MESSAGE_COUNT) -> bool:
    messages = load_messages(session_id, limit=100)
    return len(messages) >= trigger_message_count and len(messages) % trigger_message_count == 0

def summarize_conversation(session_id: str, model: str = DEFAULT_SUMMARY_MODEL) -> Optional[str]:
    messages = load_messages(session_id, limit=100)
    if not messages:
        return None
    latest = load_latest_conversation_summary(session_id)
    existing = latest.get("summary_text") if latest else None
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Summarize this procurement conversation for future follow-up context. Preserve product, quantity, required date, recommendation, supplier explanations, overrides, effective plan, unresolved questions, and PR/PO status. Exclude unrelated content."),
        ("human", "Existing summary:\n{existing}\n\nMessages:\n{messages}"),
    ])
    response = (prompt | ChatOpenAI(model=model, temperature=0.0)).invoke({"existing": existing or "No existing summary.", "messages": _dump(messages)})
    summary = response.content if hasattr(response, "content") else str(response)
    save_conversation_summary(session_id=session_id, summary_text=summary, messages_covered=len(messages), metadata={"version": "conversation_summarizer_v1", "message_count": len(messages)})
    return summary
