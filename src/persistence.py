"""
Persistence Layer for ForgeForce Procurement Workflow
Version: persistence_v2_session_safe

This version is designed to coexist with the existing ForgeForce ERP schema.
It does NOT modify or reuse the existing tables:
- users
- activity_log

Instead, it creates separate session/workflow tables:
- app_users
- app_procurement_sessions
- app_workflow_runs
- app_conversation_messages
- app_conversation_summaries
- app_decision_overrides
- app_session_activity_log

Use locally as:
    src/persistence.py
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "forgeforce_procurement.db"
PERSISTENCE_VERSION = "persistence_v4_entity_index | persisted-conversation-entity-index"


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
    return json.dumps(data, default=str, ensure_ascii=False)


def from_json(data: Optional[str]) -> Any:
    if data is None:
        return None
    try:
        return json.loads(data)
    except Exception:
        return data


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


# ============================================================
# DB Initialization
# ============================================================

def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """
    Create only the application/session persistence tables.
    This intentionally avoids table names that already exist in the ERP schema.
    """
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
            FOREIGN KEY(app_user_id) REFERENCES app_users(app_user_id)
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
            FOREIGN KEY(session_id) REFERENCES app_procurement_sessions(session_id)
        )
        """)

        # Schema migration for databases created before persistence_v4.
        workflow_columns = {
            row["name"]
            for row in cur.execute("PRAGMA table_info(app_workflow_runs)").fetchall()
        }
        if "entity_index_json" not in workflow_columns:
            cur.execute(
                "ALTER TABLE app_workflow_runs ADD COLUMN entity_index_json TEXT"
            )

        cur.execute("""
        CREATE TABLE IF NOT EXISTS app_conversation_messages (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES app_procurement_sessions(session_id)
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
            FOREIGN KEY(session_id) REFERENCES app_procurement_sessions(session_id)
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
            FOREIGN KEY(session_id) REFERENCES app_procurement_sessions(session_id),
            FOREIGN KEY(run_id) REFERENCES app_workflow_runs(run_id)
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
            FOREIGN KEY(session_id) REFERENCES app_procurement_sessions(session_id),
            FOREIGN KEY(run_id) REFERENCES app_workflow_runs(run_id)
        )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_users_email ON app_users(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_proc_sessions_user ON app_procurement_sessions(app_user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_workflow_runs_session ON app_workflow_runs(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_conversation_messages_session ON app_conversation_messages(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_session_activity_session ON app_session_activity_log(session_id)")

        conn.commit()


# ============================================================
# Users / Sessions
# ============================================================

def get_app_user_by_email(email: str, db_path: Path | str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    email = normalize_email(email)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM app_users WHERE email = ?", (email,)).fetchone()
        return row_to_dict(row)


def get_or_create_app_user(
    email: str,
    display_name: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    email = normalize_email(email)
    if not email or "@" not in email:
        raise ValueError("A valid email address is required.")

    existing = get_app_user_by_email(email, db_path)
    if existing:
        return existing

    now = utc_now()
    user = {
        "app_user_id": generate_user_id(),
        "email": email,
        "display_name": display_name,
        "created_at": now,
        "updated_at": now,
    }

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_users (app_user_id, email, display_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["app_user_id"], user["email"], user["display_name"], user["created_at"], user["updated_at"]),
        )
        conn.commit()

    return user


def create_procurement_session(
    app_user_id: str,
    product_id: Optional[str] = None,
    demand_forecast: Optional[float] = None,
    required_date: Optional[str] = None,
    title: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    now = utc_now()
    session_id = generate_session_id()
    title = title or (f"{product_id} | Qty {demand_forecast} | Due {required_date}" if product_id and required_date else f"Procurement Session {session_id}")

    session = {
        "session_id": session_id,
        "app_user_id": app_user_id,
        "title": title,
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
            INSERT INTO app_procurement_sessions
            (session_id, app_user_id, title, product_id, demand_forecast, required_date, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, app_user_id, title, product_id, demand_forecast, required_date, "active", now, now),
        )
        conn.commit()

    return session


def list_user_sessions(app_user_id: str, limit: int = 20, db_path: Path | str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM app_procurement_sessions
            WHERE app_user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (app_user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_session(session_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM app_procurement_sessions WHERE session_id = ?", (session_id,)).fetchone()
        return row_to_dict(row)


def touch_session(session_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute("UPDATE app_procurement_sessions SET updated_at = ? WHERE session_id = ?", (utc_now(), session_id))
        conn.commit()


# ============================================================
# Workflow Runs
# ============================================================

def get_next_run_number(session_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(run_number), 0) AS max_run FROM app_workflow_runs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return int(row["max_run"]) + 1


def save_workflow_run(
    session_id: str,
    final_state: Dict[str, Any],
    input_payload: Optional[Dict[str, Any]] = None,
    entity_index: Optional[Dict[str, Any]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    if final_state is None:
        raise ValueError("final_state is required")

    now = utc_now()
    run_id = generate_run_id()
    run_number = get_next_run_number(session_id, db_path)
    input_payload = input_payload or {
        "product_id": final_state.get("product_id"),
        "demand_forecast": final_state.get("demand_forecast"),
        "required_date": final_state.get("current_date"),
    }

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_workflow_runs (
                run_id, session_id, run_number, input_json, final_state_json,
                demand_analysis_json, supplier_intelligence_json, risk_complexity_plan_json,
                contracted_reasoning_json, spot_reasoning_json, decision_aggregation_json,
                entity_index_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                run_number,
                to_json(input_payload),
                to_json(final_state),
                to_json(final_state.get("demand_analysis")),
                to_json(final_state.get("supplier_intelligence_output")),
                to_json(final_state.get("risk_complexity_plan")),
                to_json(final_state.get("contracted_reasoning")),
                to_json(final_state.get("spot_reasoning")),
                to_json(final_state.get("decision_aggregation")),
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
            (input_payload.get("product_id"), input_payload.get("demand_forecast"), input_payload.get("required_date"), now, session_id),
        )
        conn.commit()

    return {
        "run_id": run_id,
        "session_id": session_id,
        "run_number": run_number,
        "created_at": now,
        "entity_index_saved": entity_index is not None,
    }


def save_workflow_entity_index(
    run_id: str,
    entity_index: Dict[str, Any],
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Persist or replace the compact entity index for an existing workflow run."""
    if not run_id:
        raise ValueError("run_id is required")
    if entity_index is None:
        raise ValueError("entity_index is required")

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
            raise ValueError(f"Workflow run not found: {run_id}")
        conn.commit()

    return {"run_id": run_id, "entity_index_saved": True}


def load_workflow_entity_index(
    run_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Load the persisted compact entity index for a workflow run."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT entity_index_json FROM app_workflow_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()

    if not row:
        return None
    return from_json(row["entity_index_json"])


def load_workflow_run(run_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM app_workflow_runs WHERE run_id = ?", (run_id,)).fetchone()
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
        item[key.replace("_json", "")] = from_json(item.get(key))
    return item


def load_latest_workflow_run(session_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT run_id FROM app_workflow_runs
            WHERE session_id = ?
            ORDER BY run_number DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    return load_workflow_run(row["run_id"], db_path) if row else None


def list_app_workflow_runs(session_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT run_id, session_id, run_number, input_json, created_at
            FROM app_workflow_runs
            WHERE session_id = ?
            ORDER BY run_number DESC
            """,
            (session_id,),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["input"] = from_json(item.pop("input_json"))
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
    if role not in {"user", "assistant", "system"}:
        raise ValueError("role must be one of: user, assistant, system")

    now = utc_now()
    message_id = generate_message_id()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_conversation_messages (message_id, session_id, role, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, to_json(metadata or {}), now),
        )
        conn.commit()

    touch_session(session_id, db_path)
    return {"message_id": message_id, "session_id": session_id, "role": role, "content": content, "metadata": metadata or {}, "created_at": now}


def load_messages(session_id: str, limit: int = 20, db_path: Path | str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM app_conversation_messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    messages = []
    for row in reversed(rows):
        item = dict(row)
        item["metadata"] = from_json(item.pop("metadata_json"))
        messages.append(item)
    return messages


def save_conversation_summary(
    session_id: str,
    summary_text: str,
    messages_covered: int,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    now = utc_now()
    summary_id = generate_summary_id()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_conversation_summaries (summary_id, session_id, summary_text, messages_covered, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (summary_id, session_id, summary_text, messages_covered, to_json(metadata or {}), now),
        )
        conn.commit()
    return {"summary_id": summary_id, "session_id": session_id, "summary_text": summary_text, "messages_covered": messages_covered, "created_at": now}


def load_latest_conversation_summary(session_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM app_conversation_summaries
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["metadata"] = from_json(item.pop("metadata_json"))
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
    now = utc_now()
    activity_id = generate_activity_id()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_session_activity_log
            (session_activity_id, session_id, run_id, actor, action, entity_type, entity_id, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (activity_id, session_id, run_id, actor, action, entity_type, entity_id, to_json(details or {}), now),
        )
        conn.commit()
    touch_session(session_id, db_path)
    return {"session_activity_id": activity_id, "session_id": session_id, "run_id": run_id, "actor": actor, "action": action, "details": details or {}, "created_at": now}


def load_session_activity(session_id: str, limit: int = 50, db_path: Path | str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM app_session_activity_log
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    activities = []
    for row in rows:
        item = dict(row)
        item["details"] = from_json(item.pop("details_json"))
        activities.append(item)
    return activities

# ============================================================
# Latest Saved Review Retrieval
# ============================================================

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
        row = conn.execute(query, params).fetchone()

    if not row:
        return None

    item = dict(row)
    details = from_json(item.pop("details_json")) or {}
    if not isinstance(details, dict):
        details = {}

    effective_decision = details.get("effective_decision") or {}
    supplier_overrides = details.get("supplier_overrides") or {}

    return {
        "session_activity_id": item.get("session_activity_id"),
        "session_id": item.get("session_id"),
        "run_id": item.get("run_id"),
        "action": item.get("action"),
        "actor": item.get("actor"),
        "override_strategy": details.get("override_strategy") or "no_override",
        "supplier_overrides": supplier_overrides if isinstance(supplier_overrides, dict) else {},
        "override_reason": (
            details.get("override_reason")
            or (
                effective_decision.get("human_decision", {}).get("override_reason")
                if isinstance(effective_decision, dict)
                else None
            )
            or ""
        ),
        "effective_decision": effective_decision if isinstance(effective_decision, dict) else {},
        "available_strategy_options": details.get("available_strategy_options") or [],
        "created_at": item.get("created_at"),
    }



def save_decision_override(
    session_id: str,
    override_strategy: str,
    override_reason: str,
    original_strategy: Optional[str] = None,
    run_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    if not override_reason or not override_reason.strip():
        raise ValueError("override_reason is required for auditability")

    now = utc_now()
    override_id = generate_override_id()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_decision_overrides
            (override_id, session_id, run_id, original_strategy, override_strategy, override_reason, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (override_id, session_id, run_id, original_strategy, override_strategy, override_reason.strip(), to_json(metadata or {}), now),
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
            "original_strategy": original_strategy,
            "override_strategy": override_strategy,
            "override_reason": override_reason.strip(),
        },
        db_path=db_path,
    )

    return {"override_id": override_id, "session_id": session_id, "run_id": run_id, "original_strategy": original_strategy, "override_strategy": override_strategy, "override_reason": override_reason.strip(), "created_at": now}


def log_pr_initialized(session_id: str, run_id: Optional[str], pr_payload: Dict[str, Any], db_path: Path | str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    return save_session_activity(
        session_id=session_id,
        run_id=run_id,
        actor="human",
        action="pr_initialized",
        entity_type="purchase_requisition",
        entity_id=pr_payload.get("pr_id") if isinstance(pr_payload, dict) else None,
        details=pr_payload,
        db_path=db_path,
    )


# ============================================================
# Smoke Test
# ============================================================

if __name__ == "__main__":
    print("Persistence Version:", PERSISTENCE_VERSION)
    print("Database Path:", DEFAULT_DB_PATH)

    init_db()

    user = get_or_create_app_user("test@example.com", "Test User")
    print("User:", user)

    sessions = list_user_sessions(user["app_user_id"])
    if sessions:
        session = sessions[0]
    else:
        session = create_procurement_session(
            app_user_id=user["app_user_id"],
            product_id="RS-240",
            demand_forecast=80,
            required_date="2026-07-15",
        )
    print("Session:", session)

    save_message(session["session_id"], "user", "Run procurement analysis for RS-240.")
    print("Messages:", load_messages(session["session_id"]))

    save_session_activity(session["session_id"], action="smoke_test", details={"status": "ok"})
    print("Session Activity:", load_session_activity(session["session_id"]))
