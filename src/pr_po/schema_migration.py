from __future__ import annotations
import hashlib
from pr_po.db import get_connection

DEMO_APPROVAL_CODES = {"U004":"4804","U005":"2505","U006":"5006","U008":"1008"}

def _column_exists(conn, table_name, column_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)

def _add_column_if_missing(conn, table_name, column_name, definition):
    if not _column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

def _hash_code(user_id, code):
    return hashlib.sha256(f"{user_id}:{code}".encode()).hexdigest()

def migrate_pr_po_schema():
    with get_connection() as conn:
        for name, definition in [
            ("source_session_id","TEXT"),("source_run_id","TEXT"),("product_id","TEXT"),
            ("demand_forecast","REAL"),("effective_strategy","TEXT"),("approval_notes","TEXT"),
            ("rejected_by","TEXT"),("rejected_at","TIMESTAMP"),("po_created_at","TIMESTAMP")
        ]:
            _add_column_if_missing(conn, "purchase_requisitions", name, definition)

        for name, definition in [
            ("supplier_id","TEXT"),("supplier_name","TEXT"),("procurement_strategy","TEXT"),
            ("lead_time_days","INTEGER"),("estimated_delivery_date","DATE"),
            ("line_total_usd","REAL"),("reasoning_snapshot","TEXT")
        ]:
            _add_column_if_missing(conn, "pr_lines", name, definition)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_approval_credentials (
                user_id TEXT PRIMARY KEY,
                approval_code_hash TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pr_execution_log (
                execution_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pr_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor_user_id TEXT,
                details_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pr_id) REFERENCES purchase_requisitions(pr_id),
                FOREIGN KEY (actor_user_id) REFERENCES users(user_id)
            )
        """)
        for user_id, code in DEMO_APPROVAL_CODES.items():
            conn.execute("""
                INSERT INTO user_approval_credentials(user_id,approval_code_hash,is_active)
                VALUES (?,?,1)
                ON CONFLICT(user_id) DO UPDATE SET approval_code_hash=excluded.approval_code_hash,is_active=1
            """,(user_id,_hash_code(user_id,code)))
        conn.commit()

if __name__ == "__main__":
    migrate_pr_po_schema()
    print("PR-to-PO schema migration complete.")
