"""
Structured debug logging for the procurement conversation pipeline.

Recommended placement:
    src/conversation/debug_logger.py

Logs are written as JSON Lines to:
    logs/conversation/<session_id>_<run_id>.jsonl

Each event includes:
- timestamp
- session_id
- run_id
- stage
- event
- payload
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


LOGGER_VERSION = "conversation_debug_logger_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except Exception:
        return str(value)


class ConversationTraceLogger:
    def __init__(
        self,
        session_id: str,
        run_id: Optional[str],
        log_root: Optional[Path] = None,
    ) -> None:
        self.session_id = session_id
        self.run_id = run_id or "NO_RUN"

        project_root = Path(__file__).resolve().parents[2]
        self.log_root = log_root or (project_root / "logs" / "conversation")
        self.log_root.mkdir(parents=True, exist_ok=True)

        safe_session = self.session_id.replace("/", "_").replace("\\", "_")
        safe_run = self.run_id.replace("/", "_").replace("\\", "_")

        self.log_path = self.log_root / f"{safe_session}_{safe_run}.jsonl"

    def log(
        self,
        stage: str,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        level: str = "INFO",
    ) -> None:
        record = {
            "timestamp": _utc_now(),
            "logger_version": LOGGER_VERSION,
            "level": level,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "stage": stage,
            "event": event,
            "payload": _json_safe(payload or {}),
        }

        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str, ensure_ascii=False))
            handle.write("\n")

    def error(
        self,
        stage: str,
        event: str,
        exc: Exception,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        error_payload = dict(payload or {})
        error_payload.update({
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        })

        self.log(
            stage=stage,
            event=event,
            payload=error_payload,
            level="ERROR",
        )

    def get_log_path(self) -> str:
        return str(self.log_path)
