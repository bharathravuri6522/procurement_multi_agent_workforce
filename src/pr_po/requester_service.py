from __future__ import annotations

import hashlib
from typing import Any, Dict

from pr_po.db import get_connection


def _requester_user_id(email: str) -> str:
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:10]
    return f"APP-{digest.upper()}"


def ensure_requester_user(app_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map the logged-in application user into the ERP users table.

    The PR schema already requires requested_by -> users.user_id, so this creates
    a stable non-approver ERP user for the logged-in application identity.
    """
    email = str(app_user.get("email") or "").strip()
    display_name = str(
        app_user.get("display_name")
        or app_user.get("name")
        or email
    ).strip()

    if not email:
        raise ValueError("The logged-in user does not have an email address.")

    user_id = _requester_user_id(email)

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO users (
                user_id,
                name,
                role,
                department,
                can_approve_up_to_usd,
                email
            )
            VALUES (?, ?, 'Procurement_Requester', 'Procurement', 0, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                email = excluded.email
        """, (
            user_id,
            display_name or email,
            email,
        ))
        conn.commit()

        row = conn.execute("""
            SELECT
                user_id,
                name,
                role,
                department,
                can_approve_up_to_usd,
                email
            FROM users
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    return dict(row)
