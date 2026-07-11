from __future__ import annotations

import json
from typing import Any, Dict

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from conversation.models import QueryAnalysis

DEFAULT_ANSWER_MODEL = "gpt-4o-mini"


def _safe_json(value: Any, max_chars: int = 22000) -> str:
    text = json.dumps(value, indent=2, default=str)
    return text if len(text) <= max_chars else text[:max_chars] + "\n...TRUNCATED..."


def generate_context_answer(question, analysis, selective_context, conversation_memory, model=DEFAULT_ANSWER_MODEL) -> str:
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
You are a senior procurement decision explanation assistant.
Use only the supplied selective context. Never invent or infer missing supplier facts.

General rules:
- Match the depth to the user intent; do not repeat the same full report each time.
- Existing agent reasoning is concise evidence; expand it only as needed.
- If information is absent, identify the exact missing field.
- Higher overage is not automatically a benefit. Treat it as excess inventory / carrying-cost trade-off unless context explicitly says extra buffer is desired.

Intent behavior:
- supplier_selection_explanation: focus on why the requested alternative was rejected versus the selected supplier.
- supplier_recommendation_explanation: focus on why the selected supplier was chosen; mention alternatives briefly.
- supplier_comparison: focus on the named suppliers; selected supplier is only a baseline if relevant.
- all_suppliers_for_item: explain EVERY entry in supplier_records, and ensure the number discussed equals supplier_count.
- supplier_metrics: use supplier order quantity, not product demand. For discounts state threshold, discount %, applied flag, before/after price, and total cost only if present. Use plain currency formatting.
- human_override: if effective_decision is absent, state: "No supplier or strategy override has been recorded for this session."
- unknown entities: never speculate about unevaluated suppliers.

End with a concise conclusion appropriate to the question.
""",
        ),
        (
            "human",
            """
Question:
{question}

Query analysis:
{analysis}

Conversation memory:
{conversation_memory}

Selective procurement context:
{selective_context}
""",
        ),
    ])
    llm = ChatOpenAI(model=model, temperature=0.0)
    response = (prompt | llm).invoke({
        "question": question,
        "analysis": analysis.model_dump_json(indent=2),
        "conversation_memory": _safe_json(conversation_memory, 6000),
        "selective_context": _safe_json(selective_context, 22000),
    })
    return response.content if hasattr(response, "content") else str(response)
