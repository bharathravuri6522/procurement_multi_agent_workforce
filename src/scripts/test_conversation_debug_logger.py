"""
Smoke test for ConversationTraceLogger.

Run from the src directory:
    python scripts/test_conversation_debug_logger.py
"""

from __future__ import annotations

from conversation.debug_logger import (
    ConversationTraceLogger,
)
from core.config import settings


def main() -> None:
    trace = ConversationTraceLogger(
        session_id="PRC-DEBUG-TEST",
        run_id="RUN-DEBUG-TEST",
    )

    trace.log(
        stage="query_analyzer",
        event="debug_logger_smoke_test",
        payload={
            "intent": (
                "supplier_selection_explanation"
            ),
            "context_scope": (
                "specific_supplier_for_item"
            ),
            "approval_code": "SHOULD_BE_REDACTED",
            "api_key": "SHOULD_BE_REDACTED",
            "supplier_names": [
                "NSK Americas",
                "Bosch Rexroth USA",
            ],
        },
    )

    print(
        "Conversation debug enabled:",
        settings.conversation_debug_logs,
    )
    print(
        "Detailed trace path:",
        trace.get_log_path()
        or "Disabled",
    )


if __name__ == "__main__":
    main()
