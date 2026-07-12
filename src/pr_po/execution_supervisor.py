"""Deterministic execution supervisor for Purchase Requisitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from core.logging import get_logger
from core.observability import traceable_if_enabled


EXECUTION_SUPERVISOR_VERSION = (
    "pr_po_execution_supervisor_v2 | production-hardened"
)

logger = get_logger("pr_po.execution_supervisor")


@dataclass(frozen=True)
class ExecutionDecision:
    pr_id: str
    current_status: str
    next_action: str
    reason: str
    can_execute: bool


def determine_next_action(
    pr_id: str,
    status: str,
    has_purchase_orders: bool = False,
) -> ExecutionDecision:
    """Determine the next deterministic action for a Purchase Requisition."""
    if not str(pr_id or "").strip():
        raise ValueError("PR ID is required by the execution supervisor.")

    normalized = str(status or "").strip().lower()

    if normalized == "pending approval":
        decision = ExecutionDecision(
            pr_id=pr_id,
            current_status=status,
            next_action="await_approval",
            reason="The PR requires an authorized approver.",
            can_execute=False,
        )
    elif normalized == "rejected":
        decision = ExecutionDecision(
            pr_id=pr_id,
            current_status=status,
            next_action="stop_rejected",
            reason=(
                "The PR was rejected and must not generate purchase orders."
            ),
            can_execute=False,
        )
    elif normalized == "approved" and not has_purchase_orders:
        decision = ExecutionDecision(
            pr_id=pr_id,
            current_status=status,
            next_action="generate_purchase_orders",
            reason=(
                "The PR is approved and ready for supplier-specific "
                "PO generation."
            ),
            can_execute=True,
        )
    elif normalized == "po created" or has_purchase_orders:
        decision = ExecutionDecision(
            pr_id=pr_id,
            current_status=status,
            next_action="completed",
            reason="Purchase orders have already been generated.",
            can_execute=False,
        )
    else:
        decision = ExecutionDecision(
            pr_id=pr_id,
            current_status=status,
            next_action="manual_review",
            reason=(
                "The PR status is not recognized by the execution supervisor."
            ),
            can_execute=False,
        )

    logger.info(
        "pr_execution_action_selected",
        component="pr_po_execution_supervisor",
        status="success",
        payload={
            "version": EXECUTION_SUPERVISOR_VERSION,
            "has_purchase_orders": has_purchase_orders,
            **asdict(decision),
        },
    )

    return decision

@traceable_if_enabled(
    name="PR Execution Supervisor",
    run_type="tool",
    tags=["pr-po", "execution-supervisor", "deterministic"],
)
def determine_next_action_traced(
    pr_id: str,
    status: str,
    has_purchase_orders: bool = False,
) -> ExecutionDecision:
    """
    Trace the supervisor decision only inside an explicit execution workflow.

    UI status checks should call determine_next_action() directly so Streamlit
    reruns do not create standalone duplicate LangSmith traces.
    """
    return determine_next_action(
        pr_id=pr_id,
        status=status,
        has_purchase_orders=has_purchase_orders,
    )

