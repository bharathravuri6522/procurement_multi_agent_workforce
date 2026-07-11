from __future__ import annotations

from typing import Any, Dict, List

from pr_po.execution_supervisor import determine_next_action
from pr_po.po_service import (
    generate_purchase_orders,
    list_purchase_orders_for_pr,
)
from pr_po.pr_service import get_purchase_requisition


def execute_supervisor_action(pr_id: str) -> Dict[str, Any]:
    """
    Ask the execution supervisor for the next action and execute it.

    The supervisor decides. Deterministic services perform database writes.
    """
    pr = get_purchase_requisition(pr_id)
    existing_pos = list_purchase_orders_for_pr(pr_id)

    decision = determine_next_action(
        pr_id=pr_id,
        status=pr["status"],
        has_purchase_orders=bool(existing_pos),
    )

    result: Dict[str, Any] = {
        "supervisor_decision": {
            "pr_id": decision.pr_id,
            "current_status": decision.current_status,
            "next_action": decision.next_action,
            "reason": decision.reason,
            "can_execute": decision.can_execute,
        },
        "purchase_orders": existing_pos,
    }

    if decision.next_action == "generate_purchase_orders":
        result["purchase_orders"] = generate_purchase_orders(pr_id)
        result["execution_status"] = "purchase_orders_created"
        return result

    if decision.next_action == "stop_rejected":
        result["execution_status"] = "stopped_rejected"
        return result

    if decision.next_action == "completed":
        result["execution_status"] = "already_completed"
        return result

    result["execution_status"] = decision.next_action
    return result
