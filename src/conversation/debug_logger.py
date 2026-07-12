"""
Conversation-specific debug trace adapter.

Compact operational events are always emitted through the centralized
ForgeForce logger. Detailed per-session JSONL traces are written only when
conversation debug logging is explicitly enabled.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import settings
from core.logging import get_logger


LOGGER_VERSION = "conversation_debug_logger_v2 | centralized-adapter"

logger = get_logger("conversation.debug_trace")

_SENSITIVE_KEY_MARKERS = {
    "api_key",
    "apikey",
    "approval_code",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
}

_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(value: Any, fallback: str) -> str:
    normalized = str(value or fallback).strip()
    normalized = _SAFE_FILENAME_PATTERN.sub(
        "_",
        normalized,
    )
    normalized = normalized.strip("._")

    return normalized or fallback


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key or "").strip().lower()

    return any(
        marker in normalized
        for marker in _SENSITIVE_KEY_MARKERS
    )


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if _is_sensitive_key(key)
                else _redact(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_redact(item) for item in value]

    if isinstance(value, tuple):
        return [_redact(item) for item in value]

    if isinstance(value, set):
        return [_redact(item) for item in value]

    return value


def _json_safe(value: Any) -> Any:
    redacted = _redact(value)

    try:
        json.dumps(
            redacted,
            default=str,
            ensure_ascii=False,
        )
        return redacted
    except (TypeError, ValueError):
        return str(redacted)


def _truncate_payload(
    payload: Dict[str, Any],
    max_chars: int,
) -> Dict[str, Any]:
    safe_payload = _json_safe(payload)

    encoded = json.dumps(
        safe_payload,
        default=str,
        ensure_ascii=False,
    )

    if len(encoded) <= max_chars:
        return safe_payload

    return {
        "truncated": True,
        "original_character_count": len(encoded),
        "preview": encoded[:max_chars],
    }


def _payload_summary(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a compact central-log summary without copying the full debug payload.
    """
    safe_payload = _json_safe(payload)

    if not isinstance(safe_payload, dict):
        return {
            "payload_type": type(
                safe_payload
            ).__name__,
        }

    summary: Dict[str, Any] = {
        "payload_keys": sorted(
            safe_payload.keys()
        ),
    }

    for key in (
        "context_scope",
        "intent",
        "source",
        "should_summarize",
        "item_count",
        "supplier_count",
    ):
        if key in safe_payload:
            summary[key] = safe_payload[key]

    return summary


class ConversationTraceLogger:
    """
    Compatibility adapter for detailed conversation-pipeline tracing.

    Public methods are preserved:
    - log(...)
    - error(...)
    - get_log_path()
    """

    def __init__(
        self,
        session_id: str,
        run_id: Optional[str],
        log_root: Optional[Path] = None,
    ) -> None:
        self.session_id = session_id
        self.run_id = run_id or "NO_RUN"
        self.enabled = bool(
            getattr(
                settings,
                "conversation_debug_logs",
                False,
            )
        )
        self.max_payload_chars = max(
            1000,
            int(
                getattr(
                    settings,
                    "conversation_debug_max_payload_chars",
                    20000,
                )
            ),
        )

        configured_log_directory = Path(
            getattr(
                settings,
                "log_directory",
                Path(__file__).resolve().parents[2]
                / "logs",
            )
        )

        self.log_root = (
            Path(log_root)
            if log_root is not None
            else configured_log_directory
            / "conversation"
        )

        safe_session = _safe_filename(
            self.session_id,
            "NO_SESSION",
        )
        safe_run = _safe_filename(
            self.run_id,
            "NO_RUN",
        )

        self.log_path = (
            self.log_root
            / f"{safe_session}_{safe_run}.jsonl"
        )

        if self.enabled:
            self.log_root.mkdir(
                parents=True,
                exist_ok=True,
            )

    def log(
        self,
        stage: str,
        event: str,
        payload: Optional[
            Dict[str, Any]
        ] = None,
        level: str = "INFO",
    ) -> None:
        payload_value = payload or {}
        compact_payload = {
            "stage": stage,
            **_payload_summary(payload_value),
            "detailed_trace_enabled": (
                self.enabled
            ),
        }

        normalized_level = (
            level.strip().upper()
            if level
            else "INFO"
        )

        if normalized_level == "DEBUG":
            log_method = getattr(
                logger,
                "debug",
                logger.info,
            )
        elif normalized_level == "WARNING":
            log_method = getattr(
                logger,
                "warning",
                logger.info,
            )
        elif normalized_level in {
            "ERROR",
            "CRITICAL",
        }:
            log_method = logger.error
        else:
            log_method = logger.info

        log_method(
            event,
            component=(
                "conversation_debug_trace"
            ),
            status=(
                "failed"
                if normalized_level
                in {"ERROR", "CRITICAL"}
                else "success"
            ),
            payload=compact_payload,
        )

        if not self.enabled:
            return

        record = {
            "timestamp": _utc_now(),
            "logger_version": (
                LOGGER_VERSION
            ),
            "level": normalized_level,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "stage": stage,
            "event": event,
            "payload": _truncate_payload(
                payload_value,
                self.max_payload_chars,
            ),
        }

        with self.log_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    record,
                    default=str,
                    ensure_ascii=False,
                )
            )
            handle.write("\n")

    def error(
        self,
        stage: str,
        event: str,
        exc: Exception,
        payload: Optional[
            Dict[str, Any]
        ] = None,
    ) -> None:
        error_payload = dict(payload or {})
        error_payload.update({
            "exception_type": (
                type(exc).__name__
            ),
            "exception_message": str(exc),
        })

        self.log(
            stage=stage,
            event=event,
            payload=error_payload,
            level="ERROR",
        )

    def get_log_path(self) -> str:
        """
        Return the detailed trace path, or an empty string when disabled.
        """
        return (
            str(self.log_path)
            if self.enabled
            else ""
        )
