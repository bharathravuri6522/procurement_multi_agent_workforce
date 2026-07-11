from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ExecutionDecision:
    pr_id: str
    current_status: str
    next_action: str
    reason: str
    can_execute: bool

def determine_next_action(pr_id: str, status: str, has_purchase_orders: bool = False) -> ExecutionDecision:
    normalized = (status or "").strip().lower()
    if normalized == "pending approval":
        return ExecutionDecision(pr_id, status, "await_approval", "The PR requires an authorized approver.", False)
    if normalized == "rejected":
        return ExecutionDecision(pr_id, status, "stop_rejected", "The PR was rejected and must not generate purchase orders.", False)
    if normalized == "approved" and not has_purchase_orders:
        return ExecutionDecision(pr_id, status, "generate_purchase_orders", "The PR is approved and ready for supplier-specific PO generation.", True)
    if normalized == "po created" or has_purchase_orders:
        return ExecutionDecision(pr_id, status, "completed", "Purchase orders have already been generated.", False)
    return ExecutionDecision(pr_id, status, "manual_review", "The PR status is not recognized by the execution supervisor.", False)
