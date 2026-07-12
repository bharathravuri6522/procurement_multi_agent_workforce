"""Purchase Order generation and retrieval services."""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, DefaultDict, Dict, List

from core.logging import get_logger
from core.observability import traceable_if_enabled
from pr_po.db import get_connection
from pr_po.pr_service import get_purchase_requisition


logger = get_logger("pr_po.po_service")


class POServiceError(ValueError):
    """Raised when Purchase Order processing fails."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_po_id() -> str:
    return (
        f"PO-{datetime.now().year}-"
        f"{uuid.uuid4().hex[:8].upper()}"
    )


def list_purchase_orders_for_pr(
    pr_id: str,
) -> List[Dict[str, Any]]:
    """Return all Purchase Orders generated from a PR."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                po.*,
                s.name AS supplier_name
            FROM purchase_orders po
            LEFT JOIN suppliers s
              ON s.supplier_id = po.supplier_id
            WHERE po.pr_id = ?
            ORDER BY po.created_at
            """,
            (pr_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_po_lines(
    po_id: str,
) -> List[Dict[str, Any]]:
    """Return line items for one Purchase Order."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM po_lines
            WHERE po_id = ?
            ORDER BY po_line_id
            """,
            (po_id,),
        ).fetchall()

    return [dict(row) for row in rows]


@traceable_if_enabled(
    name="Generate Purchase Orders",
    run_type="tool",
    tags=["pr-po", "purchase-order", "generate"],
)
def generate_purchase_orders(
    pr_id: str,
) -> List[Dict[str, Any]]:
    """Generate one PO per supplier for an approved PR, idempotently."""
    started_at = time.perf_counter()
    pr = get_purchase_requisition(pr_id)
    existing = list_purchase_orders_for_pr(pr_id)
    log_context = {
        "pr_id": pr_id,
        "session_id": pr.get("source_session_id"),
        "run_id": pr.get("source_run_id"),
        "product_id": pr.get("product_id"),
        "requester_user_id": pr.get("requested_by"),
    }

    if existing:
        logger.info(
            "existing_purchase_orders_reused",
            component="pr_po_po_service",
            status="success",
            payload={
                **log_context,
                "purchase_order_count": len(existing),
            },
        )
        return existing

    if pr["status"] != "Approved":
        raise POServiceError(
            "Purchase Orders can only be generated for an Approved PR. "
            f"Current status: {pr['status']}"
        )

    grouped: DefaultDict[
        str,
        List[Dict[str, Any]],
    ] = defaultdict(list)

    for line in pr["lines"]:
        supplier_id = line.get("supplier_id")

        if not supplier_id:
            raise POServiceError(
                f"PR line {line['pr_line_id']} has no supplier_id."
            )

        grouped[supplier_id].append(line)

    if not grouped:
        raise POServiceError(
            "The approved PR does not contain supplier-assigned lines."
        )

    logger.info(
        "purchase_order_generation_started",
        component="pr_po_po_service",
        status="running",
        payload={
            **log_context,
            "supplier_count": len(grouped),
            "line_count": len(pr["lines"]),
        },
    )

    created_ids: List[str] = []

    try:
        with get_connection() as conn:
            for supplier_id, lines in grouped.items():
                po_id = _new_po_id()
                total = round(
                    sum(
                        float(
                            line.get("line_total_usd")
                            or 0
                        )
                        for line in lines
                    ),
                    2,
                )
                max_lead = max(
                    int(
                        line.get("lead_time_days")
                        or 0
                    )
                    for line in lines
                )
                expected_delivery = (
                    date.today()
                    + timedelta(days=max_lead)
                ).isoformat()

                conn.execute(
                    """
                    INSERT INTO purchase_orders (
                        po_id,
                        supplier_id,
                        pr_id,
                        status,
                        total_usd,
                        expected_delivery,
                        created_by_agent
                    )
                    VALUES (?, ?, ?, 'Created', ?, ?, 1)
                    """,
                    (
                        po_id,
                        supplier_id,
                        pr_id,
                        total,
                        expected_delivery,
                    ),
                )

                for line in lines:
                    conn.execute(
                        """
                        INSERT INTO po_lines (
                            po_id,
                            item_id,
                            quantity,
                            unit_cost_usd,
                            line_total_usd
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            po_id,
                            line["item_id"],
                            line["quantity"],
                            line[
                                "estimated_unit_cost_usd"
                            ],
                            line["line_total_usd"],
                        ),
                    )

                created_ids.append(po_id)

                logger.info(
                    "purchase_order_created",
                    component="pr_po_po_service",
                    status="success",
                    payload={
                        **log_context,
                        "po_id": po_id,
                        "supplier_id": supplier_id,
                        "line_count": len(lines),
                        "total_usd": total,
                        "expected_delivery": (
                            expected_delivery
                        ),
                    },
                )

            po_created_at = _utc_now()

            conn.execute(
                """
                UPDATE purchase_requisitions
                SET
                    status = 'PO Created',
                    po_created_at = ?
                WHERE pr_id = ?
                """,
                (po_created_at, pr_id),
            )

            conn.execute(
                """
                INSERT INTO pr_execution_log (
                    pr_id,
                    action,
                    details_json
                )
                VALUES (?, 'purchase_orders_created', ?)
                """,
                (
                    pr_id,
                    json.dumps(
                        {
                            "po_ids": created_ids,
                            "supplier_count": len(grouped),
                            "po_created_at": po_created_at,
                        }
                    ),
                ),
            )
            conn.commit()

        logger.info(
            "pr_status_changed",
            component="pr_po_po_service",
            status="success",
            payload={
                **log_context,
                "previous_status": "Approved",
                "new_status": "PO Created",
                "changed_by": "execution_supervisor",
                "changed_at": po_created_at,
                "reason": "supplier_purchase_orders_generated",
            },
        )

    except Exception as exc:
        logger.exception(
            "purchase_order_generation_failed",
            error=exc,
            component="pr_po_po_service",
            status="failed",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            payload={
                **log_context,
                "supplier_count": len(grouped),
                "created_po_count_before_failure": len(
                    created_ids
                ),
            },
        )
        raise POServiceError(
            f"Purchase Order generation failed for {pr_id}."
        ) from exc

    purchase_orders = list_purchase_orders_for_pr(
        pr_id
    )

    po_total = round(
        sum(
            float(po.get("total_usd") or 0)
            for po in purchase_orders
        ),
        2,
    )
    source_pr_total = round(
        float(pr.get("total_estimated_usd") or 0),
        2,
    )
    difference = round(
        po_total - source_pr_total,
        2,
    )

    logger.info(
        "purchase_order_generation_completed",
        component="pr_po_po_service",
        status="success",
        duration_ms=(time.perf_counter() - started_at) * 1000,
        payload={
            **log_context,
            "purchase_order_count": len(
                purchase_orders
            ),
            "supplier_count": len(grouped),
            "total_value_usd": po_total,
            "source_pr_total_usd": source_pr_total,
            "po_total_matches_pr": abs(difference) <= 0.01,
            "difference_usd": difference,
        },
    )

    return purchase_orders
