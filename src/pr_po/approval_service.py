"""Approval and rejection services for Purchase Requisitions."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.logging import get_logger
from core.observability import (
    build_trace_metadata,
    langsmith_extra as build_langsmith_extra,
    traceable_if_enabled,
)
from pr_po.db import get_connection


ALLOWED_APPROVER_ROLES = {
    "Procurement_Executive",
    "Procurement_Manager",
    "Plant_Head",
    "Director",
}

logger = get_logger("pr_po.approval_service")


class ApprovalError(ValueError):
    """Raised when PR approval or rejection validation fails."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()




def _pr_log_context(pr: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pr_id": pr.get("pr_id"),
        "session_id": pr.get("source_session_id"),
        "run_id": pr.get("source_run_id"),
        "product_id": pr.get("product_id"),
        "requester_user_id": pr.get("requested_by"),
    }


def _hash_code(user_id: str, code: str) -> str:
    return hashlib.sha256(
        f"{user_id}:{code}".encode("utf-8")
    ).hexdigest()


def get_eligible_approvers(
    pr_total: float,
    requester_user_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Return authorized approvers with sufficient approval authority."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                user_id,
                name,
                role,
                department,
                can_approve_up_to_usd
            FROM users
            WHERE can_approve_up_to_usd >= ?
            ORDER BY can_approve_up_to_usd ASC
            """,
            (pr_total,),
        ).fetchall()

    approvers = [
        dict(row)
        for row in rows
        if row["role"] in ALLOWED_APPROVER_ROLES
        and row["user_id"] != requester_user_id
    ]

    logger.info(
        "eligible_approvers_loaded",
        component="pr_po_approval_service",
        status="success",
        payload={
            "pr_total": float(pr_total or 0),
            "requester_user_id": requester_user_id,
            "eligible_approver_count": len(approvers),
        },
    )

    return approvers


def verify_approval_code(
    user_id: str,
    entered_code: str,
) -> bool:
    """Verify a submitted approval code without logging the secret value."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT approval_code_hash, is_active
            FROM user_approval_credentials
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    verified = bool(
        row
        and row["is_active"]
        and row["approval_code_hash"]
        == _hash_code(user_id, entered_code)
    )

    logger.info(
        "approval_code_verified",
        component="pr_po_approval_service",
        status="success" if verified else "failed",
        payload={
            "approver_user_id": user_id,
            "approval_code": "[REDACTED]",
            "verified": verified,
        },
    )

    return verified


def validate_approver(
    pr: Dict[str, Any],
    approver_user_id: str,
    approval_code: str,
) -> Dict[str, Any]:
    """Validate role, segregation of duties, limit, and approval code."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                user_id,
                name,
                role,
                department,
                can_approve_up_to_usd
            FROM users
            WHERE user_id = ?
            """,
            (approver_user_id,),
        ).fetchone()

    if not row:
        raise ApprovalError("Approver was not found.")

    user = dict(row)

    if user["role"] not in ALLOWED_APPROVER_ROLES:
        raise ApprovalError(
            "This user role is not authorized to approve PRs."
        )

    if user["user_id"] == pr["requested_by"]:
        raise ApprovalError(
            "The requester cannot approve their own PR."
        )

    if float(user["can_approve_up_to_usd"] or 0) < float(
        pr["total_estimated_usd"] or 0
    ):
        raise ApprovalError(
            "The approver's approval limit is insufficient."
        )

    if not verify_approval_code(
        approver_user_id,
        approval_code,
    ):
        raise ApprovalError("Approval code is invalid.")

    logger.info(
        "approver_validated",
        component="pr_po_approval_service",
        status="success",
        payload={
            **_pr_log_context(pr),
            "approver_user_id": approver_user_id,
            "approver_role": user["role"],
            "approval_limit_usd": float(
                user["can_approve_up_to_usd"] or 0
            ),
            "pr_total_usd": float(
                pr.get("total_estimated_usd") or 0
            ),
        },
    )

    return user


@traceable_if_enabled(
    name="Approve Purchase Requisition",
    run_type="chain",
    tags=["pr-po", "approval", "approve"],
)
def _approve_pr_traced(
    pr_id: str,
    approver_user_id: str,
    approval_code: str,
    approval_note: Optional[str] = None,
    *,
    langsmith_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Approve a pending PR and automatically execute the next action."""
    started_at = time.perf_counter()

    logger.info(
        "pr_approval_started",
        component="pr_po_approval_service",
        status="running",
        payload={
            "pr_id": pr_id,
            "approver_user_id": approver_user_id,
            "approval_code": "[REDACTED]",
        },
    )

    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM purchase_requisitions
                WHERE pr_id = ?
                """,
                (pr_id,),
            ).fetchone()

            if not row:
                raise ApprovalError(
                    "Purchase Requisition was not found."
                )

            pr = dict(row)

            if pr["status"] != "Pending Approval":
                raise ApprovalError(
                    "Only Pending Approval PRs can be approved. "
                    f"Current status: {pr['status']}"
                )

            approver = validate_approver(
                pr=pr,
                approver_user_id=approver_user_id,
                approval_code=approval_code,
            )

            approved_at = _utc_now()

            conn.execute(
                """
                UPDATE purchase_requisitions
                SET
                    status = 'Approved',
                    approved_by = ?,
                    approved_at = ?,
                    approval_notes = ?
                WHERE pr_id = ?
                """,
                (
                    approver_user_id,
                    approved_at,
                    approval_note,
                    pr_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO pr_execution_log (
                    pr_id,
                    action,
                    actor_user_id,
                    details_json
                )
                VALUES (?, 'pr_approved', ?, ?)
                """,
                (
                    pr_id,
                    approver_user_id,
                    json.dumps(
                        {
                            "approver_name": approver["name"],
                            "approved_at": approved_at,
                        }
                    ),
                ),
            )
            conn.commit()

        logger.info(
            "pr_status_changed",
            component="pr_po_approval_service",
            status="success",
            payload={
                **_pr_log_context(pr),
                "previous_status": "Pending Approval",
                "new_status": "Approved",
                "changed_by": approver_user_id,
                "changed_at": approved_at,
            },
        )

        from pr_po.execution_orchestrator import execute_supervisor_action

        result = execute_supervisor_action(pr_id)

    except Exception as exc:
        logger.exception(
            "pr_approval_failed",
            error=exc,
            component="pr_po_approval_service",
            status="failed",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            payload={
                "pr_id": pr_id,
                "approver_user_id": approver_user_id,
                "approval_code": "[REDACTED]",
            },
        )
        raise

    logger.info(
        "pr_approval_completed",
        component="pr_po_approval_service",
        status="success",
        duration_ms=(time.perf_counter() - started_at) * 1000,
        payload={
            **_pr_log_context(pr),
            "approver_user_id": approver_user_id,
            "execution_status": result.get("execution_status"),
            "purchase_order_count": len(
                result.get("purchase_orders") or []
            ),
        },
    )

    return result


def approve_pr(
    pr_id: str,
    approver_user_id: str,
    approval_code: str,
    approval_note: Optional[str] = None,
) -> Dict[str, Any]:
    """Approve a PR under one parent trace containing execution and PO children."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM purchase_requisitions WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()
    pr = dict(row) if row else {}
    trace_extra = build_langsmith_extra(
        metadata=build_trace_metadata(
            session_id=pr.get("source_session_id"),
            run_id=pr.get("source_run_id"),
            product_id=pr.get("product_id"),
            component="pr_po_approval_service",
            pr_id=pr_id,
            requester_user_id=pr.get("requested_by"),
            approver_user_id=approver_user_id,
        ),
        tags=["pr-po", "approval", "workflow"],
        run_name="Approve Purchase Requisition",
    )
    return _approve_pr_traced(
        pr_id=pr_id,
        approver_user_id=approver_user_id,
        approval_code=approval_code,
        approval_note=approval_note,
        langsmith_extra=trace_extra,
    )


@traceable_if_enabled(
    name="Reject Purchase Requisition",
    run_type="tool",
    tags=["pr-po", "approval", "reject"],
)
def reject_pr(
    pr_id: str,
    approver_user_id: str,
    approval_code: str,
    rejection_reason: str,
) -> Dict[str, Any]:
    """Reject a pending PR and stop further PO execution."""
    started_at = time.perf_counter()

    if not rejection_reason.strip():
        raise ApprovalError(
            "A rejection reason is required."
        )

    logger.info(
        "pr_rejection_started",
        component="pr_po_approval_service",
        status="running",
        payload={
            "pr_id": pr_id,
            "approver_user_id": approver_user_id,
            "approval_code": "[REDACTED]",
            "rejection_reason_length": len(
                rejection_reason
            ),
        },
    )

    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM purchase_requisitions
                WHERE pr_id = ?
                """,
                (pr_id,),
            ).fetchone()

            if not row:
                raise ApprovalError(
                    "Purchase Requisition was not found."
                )

            pr = dict(row)

            if pr["status"] != "Pending Approval":
                raise ApprovalError(
                    "Only Pending Approval PRs can be rejected. "
                    f"Current status: {pr['status']}"
                )

            validate_approver(
                pr=pr,
                approver_user_id=approver_user_id,
                approval_code=approval_code,
            )

            rejected_at = _utc_now()

            conn.execute(
                """
                UPDATE purchase_requisitions
                SET
                    status = 'Rejected',
                    rejected_by = ?,
                    rejected_at = ?,
                    approval_notes = ?
                WHERE pr_id = ?
                """,
                (
                    approver_user_id,
                    rejected_at,
                    rejection_reason,
                    pr_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO pr_execution_log (
                    pr_id,
                    action,
                    actor_user_id,
                    details_json
                )
                VALUES (?, 'pr_rejected', ?, ?)
                """,
                (
                    pr_id,
                    approver_user_id,
                    json.dumps(
                        {
                            "reason": (
                                "Rejected by authorized approver"
                            ),
                            "rejected_at": rejected_at,
                        }
                    ),
                ),
            )
            conn.commit()

        logger.info(
            "pr_status_changed",
            component="pr_po_approval_service",
            status="success",
            payload={
                **_pr_log_context(pr),
                "previous_status": "Pending Approval",
                "new_status": "Rejected",
                "changed_by": approver_user_id,
                "changed_at": rejected_at,
                "reason_recorded": True,
            },
        )

        from pr_po.execution_orchestrator import execute_supervisor_action

        result = execute_supervisor_action(pr_id)

    except Exception as exc:
        logger.exception(
            "pr_rejection_failed",
            error=exc,
            component="pr_po_approval_service",
            status="failed",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            payload={
                "pr_id": pr_id,
                "approver_user_id": approver_user_id,
                "approval_code": "[REDACTED]",
            },
        )
        raise

    logger.info(
        "pr_rejection_completed",
        component="pr_po_approval_service",
        status="success",
        duration_ms=(time.perf_counter() - started_at) * 1000,
        payload={
            **_pr_log_context(pr),
            "approver_user_id": approver_user_id,
            "execution_status": result.get("execution_status"),
        },
    )

    return result
