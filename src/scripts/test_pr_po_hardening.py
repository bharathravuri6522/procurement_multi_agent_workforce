"""Non-destructive smoke tests for the PR-to-PO hardening package."""

from __future__ import annotations

from pr_po.execution_supervisor import determine_next_action


def main() -> None:
    scenarios = [
        ("PR-TEST-001", "Pending Approval", False, "await_approval"),
        ("PR-TEST-002", "Rejected", False, "stop_rejected"),
        (
            "PR-TEST-003",
            "Approved",
            False,
            "generate_purchase_orders",
        ),
        ("PR-TEST-004", "PO Created", True, "completed"),
        ("PR-TEST-005", "Unknown", False, "manual_review"),
    ]

    for pr_id, status, has_pos, expected in scenarios:
        decision = determine_next_action(
            pr_id=pr_id,
            status=status,
            has_purchase_orders=has_pos,
        )
        assert decision.next_action == expected, (
            pr_id,
            decision.next_action,
            expected,
        )

    print("PR-to-PO deterministic supervisor smoke test passed.")


if __name__ == "__main__":
    main()
