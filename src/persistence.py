"""
Persistence layer for ForgeForce Procurement AI.

This module owns application users, procurement sessions, workflow runs,
conversation memory, review decisions, decision overrides, and session
activity. It intentionally uses application-prefixed tables so it can coexist
with the ERP-style procurement schema.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import settings
from core.logging import get_logger
from core.observability import traceable_if_enabled


PERSISTENCE_VERSION = (
    "persistence_v6 | guarded-schema-initialization"
)
DEFAULT_DB_PATH = Path(settings.database_path)

logger = get_logger("persistence")

_INITIALIZED_DATABASES: set[str] = set()
_INITIALIZATION_LOCK = threading.Lock()


class PersistenceError(RuntimeError):
    """Raised when a persistence operation cannot be completed safely."""


# ============================================================
# Helpers
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_session_id() -> str:
    return "PRC-" + uuid.uuid4().hex[:10].upper()


def generate_user_id() -> str:
    return "APPUSR-" + uuid.uuid4().hex[:10].upper()


def generate_run_id() -> str:
    return "RUN-" + uuid.uuid4().hex[:12].upper()


def generate_message_id() -> str:
    return "MSG-" + uuid.uuid4().hex[:12].upper()


def generate_summary_id() -> str:
    return "SUM-" + uuid.uuid4().hex[:12].upper()


def generate_override_id() -> str:
    return "OVR-" + uuid.uuid4().hex[:12].upper()


def generate_activity_id() -> str:
    return "SACT-" + uuid.uuid4().hex[:12].upper()


def to_json(data: Any) -> str:
    if data is None:
        return json.dumps(None)

    if hasattr(data, "model_dump"):
        data = data.model_dump()

    return json.dumps(
        data,
        default=str,
        ensure_ascii=False,
    )


def from_json(data: Optional[str]) -> Any:
    if data is None:
        return None

    try:
        return json.loads(data)
    except (TypeError, json.JSONDecodeError):
        return data


def get_connection(
    db_path: Path | str = DEFAULT_DB_PATH,
) -> sqlite3.Connection:
    resolved_path = Path(db_path)
    resolved_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        str(resolved_path),
        timeout=30,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def row_to_dict(
    row: Optional[sqlite3.Row],
) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _require_text(
    value: Optional[str],
    field_name: str,
) -> str:
    normalized = (value or "").strip()

    if not normalized:
        raise ValueError(
            f"{field_name} is required."
        )

    return normalized


def _log_failure(
    event: str,
    exc: Exception,
    *,
    component: str,
    started_at: Optional[float] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    logger.exception(
        event,
        error=exc,
        component=component,
        status="failed",
        duration_ms=(
            (time.perf_counter() - started_at) * 1000
            if started_at is not None
            else None
        ),
        payload=payload or {},
    )


# ============================================================
# DB Initialization
# ============================================================

def init_db(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    force: bool = False,
) -> None:
    """
    Initialize persistence tables once per database path and Python process.

    Streamlit reruns may call this function repeatedly. After the first
    successful initialization for a database path, later calls return
    immediately. Use force=True only for explicit maintenance or tests.
    """
    resolved_path = Path(db_path).resolve()
    database_key = str(resolved_path)

    if (
        not force
        and database_key in _INITIALIZED_DATABASES
    ):
        return

    with _INITIALIZATION_LOCK:
        if (
            not force
            and database_key in _INITIALIZED_DATABASES
        ):
            return

        _initialize_schema(resolved_path)
        _INITIALIZED_DATABASES.add(
            database_key
        )


@traceable_if_enabled(
    name="Initialize Persistence Schema",
    run_type="chain",
    tags=["persistence", "schema", "sqlite"],
)
def _initialize_schema(
    db_path: Path | str,
) -> None:
    """
    Create only application/session persistence tables.

    Existing ERP tables such as users and activity_log are intentionally
    untouched.
    """
    started_at = time.perf_counter()

    logger.info(
        "persistence_schema_initialization_started",
        component="persistence",
        status="running",
        payload={
            "database_path": str(Path(db_path)),
            "persistence_version": (
                PERSISTENCE_VERSION
            ),
        },
    )

    try:
        with get_connection(db_path) as conn:
            cur = conn.cursor()

            cur.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                app_user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS app_procurement_sessions (
                session_id TEXT PRIMARY KEY,
                app_user_id TEXT NOT NULL,
                title TEXT,
                product_id TEXT,
                demand_forecast REAL,
                required_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(app_user_id)
                    REFERENCES app_users(app_user_id)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS app_workflow_runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                run_number INTEGER NOT NULL,
                input_json TEXT,
                final_state_json TEXT,
                demand_analysis_json TEXT,
                supplier_intelligence_json TEXT,
                risk_complexity_plan_json TEXT,
                contracted_reasoning_json TEXT,
                spot_reasoning_json TEXT,
                decision_aggregation_json TEXT,
                entity_index_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id)
                    REFERENCES app_procurement_sessions(session_id)
            )
            """)

            workflow_columns = {
                row["name"]
                for row in cur.execute(
                    "PRAGMA table_info(app_workflow_runs)"
                ).fetchall()
            }

            if "entity_index_json" not in workflow_columns:
                cur.execute(
                    """
                    ALTER TABLE app_workflow_runs
                    ADD COLUMN entity_index_json TEXT
                    """
                )

            cur.execute("""
            CREATE TABLE IF NOT EXISTS app_conversation_messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL
                    CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id)
                    REFERENCES app_procurement_sessions(session_id)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS app_conversation_summaries (
                summary_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                messages_covered INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id)
                    REFERENCES app_procurement_sessions(session_id)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS app_decision_overrides (
                override_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                run_id TEXT,
                original_strategy TEXT,
                override_strategy TEXT NOT NULL,
                override_reason TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id)
                    REFERENCES app_procurement_sessions(session_id),
                FOREIGN KEY(run_id)
                    REFERENCES app_workflow_runs(run_id)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS app_session_activity_log (
                session_activity_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                run_id TEXT,
                actor TEXT,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                details_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id)
                    REFERENCES app_procurement_sessions(session_id),
                FOREIGN KEY(run_id)
                    REFERENCES app_workflow_runs(run_id)
            )
            """)

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_app_users_email
                ON app_users(email)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_app_proc_sessions_user
                ON app_procurement_sessions(app_user_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_app_workflow_runs_session
                ON app_workflow_runs(session_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_app_conversation_messages_session
                ON app_conversation_messages(session_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_app_session_activity_session
                ON app_session_activity_log(session_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_app_session_activity_run
                ON app_session_activity_log(run_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_app_review_activity
                ON app_session_activity_log(
                    session_id,
                    run_id,
                    action,
                    created_at
                )
                """
            )

            conn.commit()

    except Exception as exc:
        _log_failure(
            "persistence_schema_initialization_failed",
            exc,
            component="persistence",
            started_at=started_at,
            payload={
                "database_path": str(Path(db_path)),
            },
        )
        raise PersistenceError(
            "Persistence schema initialization failed."
        ) from exc

    logger.info(
        "persistence_schema_initialization_completed",
        component="persistence",
        status="success",
        duration_ms=(
            time.perf_counter() - started_at
        ) * 1000,
        payload={
            "database_path": str(Path(db_path)),
            "persistence_version": (
                PERSISTENCE_VERSION
            ),
        },
    )


# ============================================================
# Users / Sessions
# ============================================================

def get_app_user_by_email(
    email: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    normalized_email = normalize_email(email)

    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM app_users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()

    return row_to_dict(row)


def get_or_create_app_user(
    email: str,
    display_name: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    normalized_email = normalize_email(email)

    if (
        not normalized_email
        or "@" not in normalized_email
    ):
        raise ValueError(
            "A valid email address is required."
        )

    existing = get_app_user_by_email(
        normalized_email,
        db_path,
    )

    if existing:
        return existing

    now = utc_now()
    user = {
        "app_user_id": generate_user_id(),
        "email": normalized_email,
        "display_name": (
            display_name.strip()
            if display_name
            else None
        ),
        "created_at": now,
        "updated_at": now,
    }

    try:
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO app_users (
                    app_user_id,
                    email,
                    display_name,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user["app_user_id"],
                    user["email"],
                    user["display_name"],
                    user["created_at"],
                    user["updated_at"],
                ),
            )
            conn.commit()

    except sqlite3.IntegrityError:
        concurrent = get_app_user_by_email(
            normalized_email,
            db_path,
        )
        if concurrent:
            return concurrent
        raise

    logger.info(
        "app_user_ready",
        component="persistence",
        status="success",
        payload={
            "app_user_id": user["app_user_id"],
            "has_display_name": bool(
                user["display_name"]
            ),
        },
    )

    return user


def create_procurement_session(
    app_user_id: str,
    product_id: Optional[str] = None,
    demand_forecast: Optional[float] = None,
    required_date: Optional[str] = None,
    title: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    _require_text(
        app_user_id,
        "app_user_id",
    )

    now = utc_now()
    session_id = generate_session_id()
    resolved_title = title or (
        f"{product_id} | Qty {demand_forecast} | Due {required_date}"
        if product_id and required_date
        else f"Procurement Session {session_id}"
    )

    session = {
        "session_id": session_id,
        "app_user_id": app_user_id,
        "title": resolved_title,
        "product_id": product_id,
        "demand_forecast": demand_forecast,
        "required_date": required_date,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_procurement_sessions (
                session_id,
                app_user_id,
                title,
                product_id,
                demand_forecast,
                required_date,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                app_user_id,
                resolved_title,
                product_id,
                demand_forecast,
                required_date,
                "active",
                now,
                now,
            ),
        )
        conn.commit()

    logger.info(
        "procurement_session_created",
        component="persistence",
        status="success",
        payload={
            "session_id": session_id,
            "app_user_id": app_user_id,
            "product_id": product_id,
        },
    )

    return session


def list_user_sessions(
    app_user_id: str,
    limit: int = 20,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM app_procurement_sessions
            WHERE app_user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (app_user_id, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def get_session(
    session_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM app_procurement_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

    return row_to_dict(row)


def touch_session(
    session_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE app_procurement_sessions
            SET updated_at = ?
            WHERE session_id = ?
            """,
            (utc_now(), session_id),
        )
        conn.commit()


# ============================================================
# Workflow Runs
# ============================================================

def get_next_run_number(
    session_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(run_number), 0) AS max_run
            FROM app_workflow_runs
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

    return int(row["max_run"]) + 1


@traceable_if_enabled(
    name="Save Workflow Run",
    run_type="chain",
    tags=["persistence", "workflow", "save"],
)
def save_workflow_run(
    session_id: str,
    final_state: Dict[str, Any],
    input_payload: Optional[Dict[str, Any]] = None,
    entity_index: Optional[Dict[str, Any]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    if final_state is None:
        raise ValueError(
            "final_state is required"
        )

    started_at = time.perf_counter()
    now = utc_now()
    run_id = generate_run_id()
    run_number = get_next_run_number(
        session_id,
        db_path,
    )
    resolved_input = input_payload or {
        "product_id": final_state.get(
            "product_id"
        ),
        "demand_forecast": final_state.get(
            "demand_forecast"
        ),
        "required_date": final_state.get(
            "current_date"
        ),
    }

    logger.info(
        "workflow_run_save_started",
        component="persistence",
        status="running",
        payload={
            "session_id": session_id,
            "run_id": run_id,
            "run_number": run_number,
            "product_id": resolved_input.get(
                "product_id"
            ),
        },
    )

    try:
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO app_workflow_runs (
                    run_id,
                    session_id,
                    run_number,
                    input_json,
                    final_state_json,
                    demand_analysis_json,
                    supplier_intelligence_json,
                    risk_complexity_plan_json,
                    contracted_reasoning_json,
                    spot_reasoning_json,
                    decision_aggregation_json,
                    entity_index_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    run_number,
                    to_json(resolved_input),
                    to_json(final_state),
                    to_json(
                        final_state.get(
                            "demand_analysis"
                        )
                    ),
                    to_json(
                        final_state.get(
                            "supplier_intelligence_output"
                        )
                    ),
                    to_json(
                        final_state.get(
                            "risk_complexity_plan"
                        )
                    ),
                    to_json(
                        final_state.get(
                            "contracted_reasoning"
                        )
                    ),
                    to_json(
                        final_state.get(
                            "spot_reasoning"
                        )
                    ),
                    to_json(
                        final_state.get(
                            "decision_aggregation"
                        )
                    ),
                    to_json(entity_index),
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE app_procurement_sessions
                SET product_id = COALESCE(?, product_id),
                    demand_forecast = COALESCE(?, demand_forecast),
                    required_date = COALESCE(?, required_date),
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    resolved_input.get(
                        "product_id"
                    ),
                    resolved_input.get(
                        "demand_forecast"
                    ),
                    resolved_input.get(
                        "required_date"
                    ),
                    now,
                    session_id,
                ),
            )
            conn.commit()

    except Exception as exc:
        _log_failure(
            "workflow_run_save_failed",
            exc,
            component="persistence",
            started_at=started_at,
            payload={
                "session_id": session_id,
                "run_id": run_id,
            },
        )
        raise PersistenceError(
            "The workflow run could not be saved."
        ) from exc

    result = {
        "run_id": run_id,
        "session_id": session_id,
        "run_number": run_number,
        "created_at": now,
        "entity_index_saved": (
            entity_index is not None
        ),
    }

    logger.info(
        "workflow_run_save_completed",
        component="persistence",
        status="success",
        duration_ms=(
            time.perf_counter() - started_at
        ) * 1000,
        payload=result,
    )

    return result


def save_workflow_entity_index(
    run_id: str,
    entity_index: Dict[str, Any],
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    _require_text(run_id, "run_id")

    if entity_index is None:
        raise ValueError(
            "entity_index is required"
        )

    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE app_workflow_runs
            SET entity_index_json = ?
            WHERE run_id = ?
            """,
            (to_json(entity_index), run_id),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"Workflow run not found: {run_id}"
            )

        conn.commit()

    return {
        "run_id": run_id,
        "entity_index_saved": True,
    }


def load_workflow_entity_index(
    run_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT entity_index_json
            FROM app_workflow_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    if not row:
        return None

    value = from_json(
        row["entity_index_json"]
    )
    return value if isinstance(value, dict) else None


def load_workflow_run(
    run_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM app_workflow_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    if not row:
        return None

    item = dict(row)

    for key in [
        "input_json",
        "final_state_json",
        "demand_analysis_json",
        "supplier_intelligence_json",
        "risk_complexity_plan_json",
        "contracted_reasoning_json",
        "spot_reasoning_json",
        "decision_aggregation_json",
        "entity_index_json",
    ]:
        item[
            key.replace("_json", "")
        ] = from_json(item.get(key))

    return item


@traceable_if_enabled(
    name="Restore Procurement Session",
    run_type="chain",
    tags=["persistence", "workflow", "restore"],
)
def load_latest_workflow_run(
    session_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT run_id
            FROM app_workflow_runs
            WHERE session_id = ?
            ORDER BY run_number DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()

    result = (
        load_workflow_run(
            row["run_id"],
            db_path,
        )
        if row
        else None
    )

    logger.info(
        "latest_workflow_run_loaded",
        component="persistence",
        status="success",
        payload={
            "session_id": session_id,
            "run_id": (
                result.get("run_id")
                if result
                else None
            ),
            "found": bool(result),
        },
    )

    return result


def list_app_workflow_runs(
    session_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                run_id,
                session_id,
                run_number,
                input_json,
                created_at
            FROM app_workflow_runs
            WHERE session_id = ?
            ORDER BY run_number DESC
            """,
            (session_id,),
        ).fetchall()

    results: List[Dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        item["input"] = from_json(
            item.pop("input_json")
        )
        results.append(item)

    return results


# ============================================================
# Conversation + Summary
# ============================================================

def save_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    if role not in {
        "user",
        "assistant",
        "system",
    }:
        raise ValueError(
            "role must be one of: user, assistant, system"
        )

    _require_text(session_id, "session_id")
    _require_text(content, "content")

    now = utc_now()
    message_id = generate_message_id()

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_conversation_messages (
                message_id,
                session_id,
                role,
                content,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                content,
                to_json(metadata or {}),
                now,
            ),
        )
        conn.execute(
            """
            UPDATE app_procurement_sessions
            SET updated_at = ?
            WHERE session_id = ?
            """,
            (now, session_id),
        )
        conn.commit()

    return {
        "message_id": message_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
        "created_at": now,
    }


def load_messages(
    session_id: str,
    limit: int = 20,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM app_conversation_messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    messages: List[Dict[str, Any]] = []

    for row in reversed(rows):
        item = dict(row)
        item["metadata"] = from_json(
            item.pop("metadata_json")
        )
        messages.append(item)

    return messages


def save_conversation_summary(
    session_id: str,
    summary_text: str,
    messages_covered: int,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    _require_text(
        summary_text,
        "summary_text",
    )

    now = utc_now()
    summary_id = generate_summary_id()

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_conversation_summaries (
                summary_id,
                session_id,
                summary_text,
                messages_covered,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                session_id,
                summary_text,
                int(messages_covered),
                to_json(metadata or {}),
                now,
            ),
        )
        conn.commit()

    return {
        "summary_id": summary_id,
        "session_id": session_id,
        "summary_text": summary_text,
        "messages_covered": int(
            messages_covered
        ),
        "created_at": now,
    }


def load_latest_conversation_summary(
    session_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM app_conversation_summaries
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()

    if not row:
        return None

    item = dict(row)
    item["metadata"] = from_json(
        item.pop("metadata_json")
    )
    return item


# ============================================================
# Overrides + Session Activity
# ============================================================

def save_session_activity(
    session_id: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    actor: str = "system",
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    _require_text(session_id, "session_id")
    _require_text(action, "action")

    now = utc_now()
    activity_id = generate_activity_id()

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_session_activity_log (
                session_activity_id,
                session_id,
                run_id,
                actor,
                action,
                entity_type,
                entity_id,
                details_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                session_id,
                run_id,
                actor,
                action,
                entity_type,
                entity_id,
                to_json(details or {}),
                now,
            ),
        )
        conn.execute(
            """
            UPDATE app_procurement_sessions
            SET updated_at = ?
            WHERE session_id = ?
            """,
            (now, session_id),
        )
        conn.commit()

    logger.info(
        "session_activity_saved",
        component="persistence",
        status="success",
        payload={
            "session_id": session_id,
            "run_id": run_id,
            "action": action,
            "actor": actor,
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )

    return {
        "session_activity_id": activity_id,
        "session_id": session_id,
        "run_id": run_id,
        "actor": actor,
        "action": action,
        "details": details or {},
        "created_at": now,
    }


def load_session_activity(
    session_id: str,
    limit: int = 50,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM app_session_activity_log
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    activities: List[Dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        item["details"] = from_json(
            item.pop("details_json")
        )
        activities.append(item)

    return activities


# ============================================================
# Latest Saved Review Retrieval
# ============================================================

@traceable_if_enabled(
    name="Load Effective Decision",
    run_type="chain",
    tags=["persistence", "review", "effective-decision"],
)
def load_latest_review_decision(
    session_id: str,
    run_id: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    query = """
        SELECT *
        FROM app_session_activity_log
        WHERE session_id = ?
          AND action IN (
              'recommendation_approved',
              'recommendation_override_applied'
          )
    """
    params: List[Any] = [session_id]

    if run_id:
        query += " AND run_id = ?"
        params.append(run_id)

    query += " ORDER BY created_at DESC LIMIT 1"

    with get_connection(db_path) as conn:
        row = conn.execute(
            query,
            params,
        ).fetchone()

    if not row:
        logger.info(
            "review_decision_loaded",
            component="persistence",
            status="success",
            payload={
                "session_id": session_id,
                "run_id": run_id,
                "found": False,
            },
        )
        return None

    item = dict(row)
    details = from_json(
        item.pop("details_json")
    ) or {}

    if not isinstance(details, dict):
        details = {}

    effective_decision = (
        details.get("effective_decision")
        or {}
    )
    supplier_overrides = (
        details.get("supplier_overrides")
        or {}
    )

    if not isinstance(
        effective_decision,
        dict,
    ):
        effective_decision = {}

    if not isinstance(
        supplier_overrides,
        dict,
    ):
        supplier_overrides = {}

    human_decision = effective_decision.get(
        "human_decision",
        {},
    )

    if not isinstance(human_decision, dict):
        human_decision = {}

    result = {
        "session_activity_id": item.get(
            "session_activity_id"
        ),
        "session_id": item.get(
            "session_id"
        ),
        "run_id": item.get("run_id"),
        "action": item.get("action"),
        "actor": item.get("actor"),
        "override_strategy": (
            details.get("override_strategy")
            or "no_override"
        ),
        "supplier_overrides": (
            supplier_overrides
        ),
        "override_reason": (
            details.get("override_reason")
            or human_decision.get(
                "override_reason"
            )
            or ""
        ),
        "effective_decision": (
            effective_decision
        ),
        "available_strategy_options": (
            details.get(
                "available_strategy_options"
            )
            or []
        ),
        "created_at": item.get(
            "created_at"
        ),
    }

    logger.info(
        "review_decision_loaded",
        component="persistence",
        status="success",
        payload={
            "session_id": session_id,
            "run_id": result.get("run_id"),
            "action": result.get("action"),
            "supplier_override_count": len(
                supplier_overrides
            ),
            "has_override_reason": bool(
                result["override_reason"]
            ),
            "found": True,
        },
    )

    return result


@traceable_if_enabled(
    name="Save Review Decision Override",
    run_type="chain",
    tags=["persistence", "review", "override"],
)
def save_decision_override(
    session_id: str,
    override_strategy: str,
    override_reason: str,
    original_strategy: Optional[str] = None,
    run_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    reason = _require_text(
        override_reason,
        "override_reason",
    )

    now = utc_now()
    override_id = generate_override_id()

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_decision_overrides (
                override_id,
                session_id,
                run_id,
                original_strategy,
                override_strategy,
                override_reason,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                override_id,
                session_id,
                run_id,
                original_strategy,
                override_strategy,
                reason,
                to_json(metadata or {}),
                now,
            ),
        )
        conn.commit()

    save_session_activity(
        session_id=session_id,
        run_id=run_id,
        actor="human",
        action="decision_override",
        entity_type="decision_aggregation",
        entity_id=run_id,
        details={
            "override_id": override_id,
            "original_strategy": (
                original_strategy
            ),
            "override_strategy": (
                override_strategy
            ),
            "override_reason": reason,
            "metadata": metadata or {},
        },
        db_path=db_path,
    )

    result = {
        "override_id": override_id,
        "session_id": session_id,
        "run_id": run_id,
        "original_strategy": original_strategy,
        "override_strategy": (
            override_strategy
        ),
        "override_reason": reason,
        "created_at": now,
    }

    logger.info(
        "decision_override_saved",
        component="persistence",
        status="success",
        payload={
            "override_id": override_id,
            "session_id": session_id,
            "run_id": run_id,
            "original_strategy": (
                original_strategy
            ),
            "override_strategy": (
                override_strategy
            ),
            "has_metadata": bool(metadata),
        },
    )

    return result


def log_pr_initialized(
    session_id: str,
    run_id: Optional[str],
    pr_payload: Dict[str, Any],
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    return save_session_activity(
        session_id=session_id,
        run_id=run_id,
        actor="human",
        action="pr_initialized",
        entity_type="purchase_requisition",
        entity_id=(
            pr_payload.get("pr_id")
            if isinstance(pr_payload, dict)
            else None
        ),
        details=pr_payload,
        db_path=db_path,
    )


if __name__ == "__main__":
    print(
        "Persistence Version:",
        PERSISTENCE_VERSION,
    )
    print(
        "Database Path:",
        DEFAULT_DB_PATH,
    )

    init_db()
