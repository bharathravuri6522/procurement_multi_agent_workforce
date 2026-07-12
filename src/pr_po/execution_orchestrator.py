"""Execution orchestration between PR approval and PO generation."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from core.logging import get_logger
from core.observability import traceable_if_enabled
from pr_po.execution_supervisor import determine_next_action_traced
from pr_po.po_service import (
    generate_purchase_orders,
    list_purchase_orders_for_pr,
)
from pr_po.pr_service import get_purchase_requisition


EXECUTION_ORCHESTRATOR_VERSION = (
    "pr_po_execution_orchestrator_v2 | production-hardened"
)

logger = get_logger("pr_po.execution_orchestrator")


class ExecutionOrchestrationError(RuntimeError):
    """Raised when the PR-to-PO execution orchestration fails."""


def _execution_summary(
    purchase_orders: List[Dict[str, Any]],
    source_pr_total_usd: float,
) -> Dict[str, Any]:
    po_total = round(
        sum(float(po.get("total_usd") or 0) for po in purchase_orders),
        2,
    )
    source_total = round(float(source_pr_total_usd or 0), 2)
    difference = round(po_total - source_total, 2)

    return {
        "purchase_orders_created": len(purchase_orders),
        "supplier_count": len(
            {
                po.get("supplier_id")
                for po in purchase_orders
                if po.get("supplier_id")
            }
        ),
        "total_value_usd": po_total,
        "source_pr_total_usd": source_total,
        "po_total_matches_pr": abs(difference) <= 0.01,
        "difference_usd": difference,
        "completed": bool(purchase_orders),
    }


@traceable_if_enabled(
    name="PR-to-PO Execution Orchestrator",
    run_type="chain",
    tags=["pr-po", "execution-orchestrator"],
)
def execute_supervisor_action(pr_id: str) -> Dict[str, Any]:
    """Ask the supervisor for the next action and execute it safely."""
    started_at = time.perf_counter()

    logger.info(
        "pr_po_execution_started",
        component="pr_po_execution_orchestrator",
        status="running",
        payload={"pr_id": pr_id},
    )

    try:
        pr = get_purchase_requisition(pr_id)
        log_context = {
            "pr_id": pr_id,
            "session_id": pr.get("source_session_id"),
            "run_id": pr.get("source_run_id"),
            "product_id": pr.get("product_id"),
            "requester_user_id": pr.get("requested_by"),
        }
        existing_pos = list_purchase_orders_for_pr(pr_id)

        decision = determine_next_action_traced(
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
            purchase_orders = generate_purchase_orders(pr_id)
            result["purchase_orders"] = purchase_orders
            result["execution_status"] = "purchase_orders_created"
        elif decision.next_action == "stop_rejected":
            result["execution_status"] = "stopped_rejected"
        elif decision.next_action == "completed":
            result["execution_status"] = "already_completed"
        else:
            result["execution_status"] = decision.next_action

        result["execution_summary"] = _execution_summary(
            result["purchase_orders"],
            pr.get("total_estimated_usd") or 0,
        )

    except Exception as exc:
        logger.exception(
            "pr_po_execution_failed",
            error=exc,
            component="pr_po_execution_orchestrator",
            status="failed",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            payload={"pr_id": pr_id},
        )
        raise ExecutionOrchestrationError(
            f"PR-to-PO execution failed for {pr_id}."
        ) from exc

    logger.info(
        "pr_po_execution_completed",
        component="pr_po_execution_orchestrator",
        status="success",
        duration_ms=(time.perf_counter() - started_at) * 1000,
        payload={
            **log_context,
            "execution_status": result["execution_status"],
            **result["execution_summary"],
        },
    )

    return result
