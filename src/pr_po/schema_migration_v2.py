from __future__ import annotations

from pr_po.schema_migration import migrate_pr_po_schema
from pr_po.db import get_connection


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def migrate_requester_identity() -> None:
    """
    Extend the existing ERP users table with email so logged-in application
    users can be mapped into users and referenced by purchase_requisitions.
    """
    migrate_pr_po_schema()

    with get_connection() as conn:
        if not _column_exists(conn, "users", "email"):
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
            ON users(email)
            WHERE email IS NOT NULL
        """)

        conn.commit()


if __name__ == "__main__":
    migrate_requester_identity()
    print("PR-to-PO requester identity migration complete.")
