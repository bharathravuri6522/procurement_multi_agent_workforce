"""Unified schema migration for the PR-to-PO subsystem."""

from __future__ import annotations

import hashlib
from typing import Iterable, Tuple

from core.logging import get_logger
from pr_po.db import get_connection


SCHEMA_MIGRATION_VERSION = "pr_po_schema_migration_v3 | unified"

DEMO_APPROVAL_CODES = {
    "U004": "4804",
    "U005": "2505",
    "U006": "5006",
    "U008": "1008",
}

logger = get_logger("pr_po.schema_migration")


def _column_exists(
    conn,
    table_name: str,
    column_name: str,
) -> bool:
    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row["name"] == column_name
        for row in rows
    )


def _add_column_if_missing(
    conn,
    table_name: str,
    column_name: str,
    definition: str,
) -> bool:
    """Add a column when absent and return whether a change was applied."""
    if _column_exists(
        conn,
        table_name,
        column_name,
    ):
        return False

    conn.execute(
        f"ALTER TABLE {table_name} "
        f"ADD COLUMN {column_name} {definition}"
    )
    return True


def _apply_columns(
    conn,
    table_name: str,
    columns: Iterable[Tuple[str, str]],
) -> int:
    changes = 0

    for column_name, definition in columns:
        if _add_column_if_missing(
            conn,
            table_name,
            column_name,
            definition,
        ):
            changes += 1

    return changes


def _hash_code(
    user_id: str,
    code: str,
) -> str:
    return hashlib.sha256(
        f"{user_id}:{code}".encode("utf-8")
    ).hexdigest()


def migrate_pr_po_schema() -> None:
    """
    Apply all current PR-to-PO schema changes in one idempotent migration.

    This migration assumes the foundational application tables were created by
    the main database setup before it runs.
    """
    logger.info(
        "pr_po_schema_migration_started",
        component="pr_po_schema_migration",
        status="running",
        payload={
            "migration_version": SCHEMA_MIGRATION_VERSION,
        },
    )

    with get_connection() as conn:
        pr_column_changes = _apply_columns(
            conn,
            "purchase_requisitions",
            [
                ("source_session_id", "TEXT"),
                ("source_run_id", "TEXT"),
                ("product_id", "TEXT"),
                ("demand_forecast", "REAL"),
                ("effective_strategy", "TEXT"),
                ("approval_notes", "TEXT"),
                ("rejected_by", "TEXT"),
                ("rejected_at", "TIMESTAMP"),
                ("po_created_at", "TIMESTAMP"),
            ],
        )

        pr_line_column_changes = _apply_columns(
            conn,
            "pr_lines",
            [
                ("supplier_id", "TEXT"),
                ("supplier_name", "TEXT"),
                ("procurement_strategy", "TEXT"),
                ("lead_time_days", "INTEGER"),
                ("estimated_delivery_date", "DATE"),
                ("line_total_usd", "REAL"),
                ("reasoning_snapshot", "TEXT"),
            ],
        )

        user_column_changes = _apply_columns(
            conn,
            "users",
            [
                ("email", "TEXT"),
            ],
        )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
            ON users(email)
            WHERE email IS NOT NULL
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_approval_credentials (
                user_id TEXT PRIMARY KEY,
                approval_code_hash TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pr_execution_log (
                execution_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pr_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor_user_id TEXT,
                details_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pr_id)
                    REFERENCES purchase_requisitions(pr_id),
                FOREIGN KEY (actor_user_id)
                    REFERENCES users(user_id)
            )
            """
        )

        for user_id, code in DEMO_APPROVAL_CODES.items():
            conn.execute(
                """
                INSERT INTO user_approval_credentials (
                    user_id,
                    approval_code_hash,
                    is_active
                )
                VALUES (?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    approval_code_hash = excluded.approval_code_hash,
                    is_active = 1
                """,
                (
                    user_id,
                    _hash_code(user_id, code),
                ),
            )

        conn.commit()

    logger.info(
        "pr_po_schema_migration_completed",
        component="pr_po_schema_migration",
        status="success",
        payload={
            "migration_version": SCHEMA_MIGRATION_VERSION,
            "purchase_requisition_columns_added": pr_column_changes,
            "pr_line_columns_added": pr_line_column_changes,
            "user_columns_added": user_column_changes,
            "approval_credential_count": len(
                DEMO_APPROVAL_CODES
            ),
        },
    )


if __name__ == "__main__":
    migrate_pr_po_schema()
    print("Unified PR-to-PO schema migration complete.")
