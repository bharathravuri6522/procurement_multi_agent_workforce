from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

if load_dotenv is not None:
    load_dotenv(ENV_FILE, override=False)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    application_name: str
    application_version: str
    environment: str

    database_path: Path

    log_level: str
    log_directory: Path
    log_filename: str
    log_max_bytes: int
    log_backup_count: int
    log_to_console: bool
    verbose_workflow_logs: bool
    conversation_debug_logs: bool
    conversation_debug_max_payload_chars: int

    langsmith_tracing: bool
    langsmith_project: str
    langsmith_endpoint: str
    langsmith_api_key: Optional[str]
    langsmith_hide_inputs: bool
    langsmith_hide_outputs: bool
    langsmith_hide_metadata: bool

    default_llm_model: str
    conversation_llm_model: str

    @property
    def langsmith_configured(self) -> bool:
        return self.langsmith_tracing and bool(
            self.langsmith_api_key
        )


def load_settings() -> Settings:
    return Settings(
        application_name=os.getenv(
            "FORGEFORCE_APP_NAME",
            "ForgeForce Procurement AI",
        ),
        application_version=os.getenv(
            "FORGEFORCE_APP_VERSION",
            "1.0.0",
        ),
        environment=os.getenv(
            "FORGEFORCE_ENV",
            "development",
        ),
        database_path=Path(
            os.getenv(
                "FORGEFORCE_DATABASE_PATH",
                str(
                    PROJECT_ROOT
                    / "data"
                    / "forgeforce_procurement.db"
                ),
            )
        ),
        log_level=os.getenv(
            "FORGEFORCE_LOG_LEVEL",
            "INFO",
        ).upper(),
        log_directory=Path(
            os.getenv(
                "FORGEFORCE_LOG_DIR",
                str(PROJECT_ROOT / "logs"),
            )
        ),
        log_filename=os.getenv(
            "FORGEFORCE_LOG_FILE",
            "forgeforce.jsonl",
        ),
        log_max_bytes=_env_int(
            "FORGEFORCE_LOG_MAX_BYTES",
            10 * 1024 * 1024,
        ),
        log_backup_count=_env_int(
            "FORGEFORCE_LOG_BACKUP_COUNT",
            5,
        ),
        log_to_console=_env_bool(
            "FORGEFORCE_LOG_TO_CONSOLE",
            True,
        ),
        verbose_workflow_logs=_env_bool(
            "FORGEFORCE_VERBOSE_WORKFLOW_LOGS",
            False,
        ),
        conversation_debug_logs=_env_bool(
            "FORGEFORCE_CONVERSATION_DEBUG_LOGS",
            False,
        ),
        conversation_debug_max_payload_chars=_env_int(
            "FORGEFORCE_CONVERSATION_DEBUG_MAX_PAYLOAD_CHARS",
            20000,
        ),
        langsmith_tracing=_env_bool(
            "LANGSMITH_TRACING",
            False,
        ),
        langsmith_project=os.getenv(
            "LANGSMITH_PROJECT",
            "forgeforce-procurement-dev",
        ),
        langsmith_endpoint=os.getenv(
            "LANGSMITH_ENDPOINT",
            "https://api.smith.langchain.com",
        ),
        langsmith_api_key=os.getenv(
            "LANGSMITH_API_KEY"
        ),
        langsmith_hide_inputs=_env_bool(
            "LANGSMITH_HIDE_INPUTS",
            False,
        ),
        langsmith_hide_outputs=_env_bool(
            "LANGSMITH_HIDE_OUTPUTS",
            False,
        ),
        langsmith_hide_metadata=_env_bool(
            "LANGSMITH_HIDE_METADATA",
            False,
        ),
        default_llm_model=os.getenv(
            "FORGEFORCE_DEFAULT_LLM_MODEL",
            "gpt-4o-mini",
        ),
        conversation_llm_model=os.getenv(
            "FORGEFORCE_CONVERSATION_LLM_MODEL",
            "gpt-4o-mini",
        ),
    )


settings = load_settings()
