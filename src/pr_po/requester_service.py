"""Requester identity mapping for application users and ERP users."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict

from core.logging import get_logger
from pr_po.db import get_connection


logger = get_logger("pr_po.requester_service")


class RequesterServiceError(ValueError):
    """Raised when a logged-in requester cannot be mapped to ERP users."""


def _requester_user_id(email: str) -> str:
    digest = hashlib.sha256(
        email.strip().lower().encode("utf-8")
    ).hexdigest()[:10]
    return f"APP-{digest.upper()}"


def ensure_requester_user(
    app_user: Dict[str, Any],
) -> Dict[str, Any]:
    """Map a logged-in application user into the ERP users table."""
    started_at = time.perf_counter()
    email = str(app_user.get("email") or "").strip()
    display_name = str(
        app_user.get("display_name")
        or app_user.get("name")
        or email
    ).strip()

    if not email:
        raise RequesterServiceError(
            "The logged-in user does not have an email address."
        )

    user_id = _requester_user_id(email)

    try:
        with get_connection() as conn:
            conn.execute(
                """
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
                """,
                (user_id, display_name or email, email),
            )
            conn.commit()

            row = conn.execute(
                """
                SELECT
                    user_id,
                    name,
                    role,
                    department,
                    can_approve_up_to_usd,
                    email
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        if not row:
            raise RequesterServiceError(
                "Requester identity could not be loaded after persistence."
            )

    except RequesterServiceError:
        raise
    except Exception as exc:
        logger.exception(
            "requester_identity_mapping_failed",
            error=exc,
            component="pr_po_requester_service",
            status="failed",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            payload={"user_id": user_id},
        )
        raise RequesterServiceError(
            "The requester identity could not be mapped."
        ) from exc

    requester = dict(row)

    logger.info(
        "requester_identity_ready",
        component="pr_po_requester_service",
        status="success",
        duration_ms=(time.perf_counter() - started_at) * 1000,
        payload={
            "user_id": requester["user_id"],
            "role": requester["role"],
            "department": requester["department"],
        },
    )

    return requester
