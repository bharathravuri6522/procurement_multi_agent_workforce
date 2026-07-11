from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pr_po.db import get_connection


ALLOWED_APPROVER_ROLES = {
    "Procurement_Executive",
    "Procurement_Manager",
    "Plant_Head",
    "Director",
}


class ApprovalError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_code(user_id: str, code: str) -> str:
    return hashlib.sha256(f"{user_id}:{code}".encode("utf-8")).hexdigest()


def get_eligible_approvers(
    pr_total: float,
    requester_user_id: Optional[str],
) -> List[Dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                user_id,
                name,
                role,
                department,
                can_approve_up_to_usd
            FROM users
            WHERE can_approve_up_to_usd >= ?
            ORDER BY can_approve_up_to_usd ASC
        """, (pr_total,)).fetchall()

    return [
        dict(row)
        for row in rows
        if row["role"] in ALLOWED_APPROVER_ROLES
        and row["user_id"] != requester_user_id
    ]


def verify_approval_code(user_id: str, entered_code: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("""
            SELECT approval_code_hash, is_active
            FROM user_approval_credentials
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    return bool(
        row
        and row["is_active"]
        and row["approval_code_hash"] == _hash_code(user_id, entered_code)
    )


def validate_approver(
    pr: Dict,
    approver_user_id: str,
    approval_code: str,
) -> Dict:
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                user_id,
                name,
                role,
                department,
                can_approve_up_to_usd
            FROM users
            WHERE user_id = ?
        """, (approver_user_id,)).fetchone()

    if not row:
        raise ApprovalError("Approver was not found.")

    user = dict(row)

    if user["role"] not in ALLOWED_APPROVER_ROLES:
        raise ApprovalError("This user role is not authorized to approve PRs.")

    if user["user_id"] == pr["requested_by"]:
        raise ApprovalError("The requester cannot approve their own PR.")

    if float(user["can_approve_up_to_usd"] or 0) < float(
        pr["total_estimated_usd"] or 0
    ):
        raise ApprovalError("The approver's approval limit is insufficient.")

    if not verify_approval_code(approver_user_id, approval_code):
        raise ApprovalError("Approval code is invalid.")

    return user


def approve_pr(
    pr_id: str,
    approver_user_id: str,
    approval_code: str,
    approval_note: Optional[str] = None,
) -> Dict:
    """
    Approve the PR, then let the execution supervisor decide and perform the
    next business action. For an approved PR, this creates POs automatically.
    """
    with get_connection() as conn:
        row = conn.execute("""
            SELECT *
            FROM purchase_requisitions
            WHERE pr_id = ?
        """, (pr_id,)).fetchone()

        if not row:
            raise ApprovalError("Purchase Requisition was not found.")

        pr = dict(row)

        if pr["status"] != "Pending Approval":
            raise ApprovalError(
                f"Only Pending Approval PRs can be approved. "
                f"Current status: {pr['status']}"
            )

        approver = validate_approver(
            pr=pr,
            approver_user_id=approver_user_id,
            approval_code=approval_code,
        )

        conn.execute("""
            UPDATE purchase_requisitions
            SET
                status = 'Approved',
                approved_by = ?,
                approved_at = ?,
                approval_notes = ?
            WHERE pr_id = ?
        """, (
            approver_user_id,
            _utc_now(),
            approval_note,
            pr_id,
        ))

        conn.execute("""
            INSERT INTO pr_execution_log (
                pr_id,
                action,
                actor_user_id,
                details_json
            )
            VALUES (?, 'pr_approved', ?, ?)
        """, (
            pr_id,
            approver_user_id,
            f'{{"approver_name":"{approver["name"]}"}}',
        ))

        conn.commit()

    # Import locally to avoid circular module imports.
    from pr_po.execution_orchestrator import execute_supervisor_action

    return execute_supervisor_action(pr_id)


def reject_pr(
    pr_id: str,
    approver_user_id: str,
    approval_code: str,
    rejection_reason: str,
) -> Dict:
    if not rejection_reason.strip():
        raise ApprovalError("A rejection reason is required.")

    with get_connection() as conn:
        row = conn.execute("""
            SELECT *
            FROM purchase_requisitions
            WHERE pr_id = ?
        """, (pr_id,)).fetchone()

        if not row:
            raise ApprovalError("Purchase Requisition was not found.")

        pr = dict(row)

        if pr["status"] != "Pending Approval":
            raise ApprovalError(
                f"Only Pending Approval PRs can be rejected. "
                f"Current status: {pr['status']}"
            )

        validate_approver(
            pr=pr,
            approver_user_id=approver_user_id,
            approval_code=approval_code,
        )

        conn.execute("""
            UPDATE purchase_requisitions
            SET
                status = 'Rejected',
                rejected_by = ?,
                rejected_at = ?,
                approval_notes = ?
            WHERE pr_id = ?
        """, (
            approver_user_id,
            _utc_now(),
            rejection_reason,
            pr_id,
        ))

        conn.execute("""
            INSERT INTO pr_execution_log (
                pr_id,
                action,
                actor_user_id,
                details_json
            )
            VALUES (?, 'pr_rejected', ?, ?)
        """, (
            pr_id,
            approver_user_id,
            '{"reason":"Rejected by authorized approver"}',
        ))

        conn.commit()

    from pr_po.execution_orchestrator import execute_supervisor_action

    return execute_supervisor_action(pr_id)
