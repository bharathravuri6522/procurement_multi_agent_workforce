"""Purchase Requisition preview, creation, and retrieval services."""

from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from core.logging import get_logger
from core.observability import traceable_if_enabled
from pr_po.db import get_connection


logger = get_logger("pr_po.pr_service")

_LOGGED_PREVIEW_KEYS: set[tuple[Any, ...]] = set()


class PRServiceError(ValueError):
    """Raised when Purchase Requisition processing fails."""


def _new_pr_id() -> str:
    return (
        f"PR-{datetime.now().year}-"
        f"{uuid.uuid4().hex[:8].upper()}"
    )


def get_existing_pr_for_run(
    session_id: str,
    run_id: str,
) -> Optional[Dict[str, Any]]:
    """Return an existing PR for a workflow run to preserve idempotency."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM purchase_requisitions
            WHERE source_session_id = ?
              AND source_run_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id, run_id),
        ).fetchone()

    return dict(row) if row else None


def _validate_preview_inputs(
    session_id: str,
    run_id: str,
    requester_user_id: str,
    product_id: str,
) -> None:
    required_values = {
        "session_id": session_id,
        "run_id": run_id,
        "requester_user_id": requester_user_id,
        "product_id": product_id,
    }

    missing = [
        key
        for key, value in required_values.items()
        if not str(value or "").strip()
    ]

    if missing:
        raise PRServiceError(
            "Missing required PR preview fields: "
            + ", ".join(missing)
        )


def build_pr_preview(
    session_id: str,
    run_id: str,
    requester_user_id: str,
    department: str,
    product_id: str,
    demand_forecast: float,
    required_date: str,
    effective_decision: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a persistence-ready PR preview from the effective decision."""
    _validate_preview_inputs(
        session_id=session_id,
        run_id=run_id,
        requester_user_id=requester_user_id,
        product_id=product_id,
    )

    plan = effective_decision.get("effective_plan") or []
    metrics = effective_decision.get("effective_metrics") or {}
    human_decision = effective_decision.get("human_decision") or {}

    if not plan:
        raise PRServiceError(
            "The effective procurement plan is empty."
        )

    lines: List[Dict[str, Any]] = []

    for item in plan:
        item_id = item.get("item_id")
        supplier_id = item.get("selected_supplier_id")
        quantity = float(item.get("order_quantity") or 0)
        total = float(item.get("total_cost") or 0)
        lead_time = int(item.get("lead_time_days") or 0)

        if not item_id:
            raise PRServiceError(
                "An effective-plan item is missing item_id."
            )

        if not supplier_id:
            raise PRServiceError(
                f"Effective-plan item {item_id} has no selected supplier."
            )

        if quantity <= 0:
            raise PRServiceError(
                f"Effective-plan item {item_id} has an invalid order quantity."
            )

        unit_cost = total / quantity if quantity else 0

        lines.append(
            {
                "item_id": item_id,
                "item_name": item.get("item_name"),
                "supplier_id": supplier_id,
                "supplier_name": item.get(
                    "selected_supplier_name"
                ),
                "procurement_strategy": item.get("strategy"),
                "quantity": quantity,
                "unit": item.get("unit") or "EA",
                "estimated_unit_cost_usd": round(unit_cost, 6),
                "line_total_usd": round(total, 2),
                "lead_time_days": lead_time,
                "estimated_delivery_date": (
                    date.today() + timedelta(days=lead_time)
                ).isoformat(),
                "reasoning_snapshot": item.get("reasoning"),
            }
        )

    preview = {
        "session_id": session_id,
        "run_id": run_id,
        "requester_user_id": requester_user_id,
        "department": department,
        "product_id": product_id,
        "demand_forecast": demand_forecast,
        "required_date": required_date,
        "effective_strategy": human_decision.get("final_strategy"),
        "total_estimated_usd": round(
            float(metrics.get("total_procurement_cost") or 0),
            2,
        ),
        "critical_path_days": metrics.get("critical_path_days"),
        "lines": lines,
    }

    preview_log_key = (
        session_id,
        run_id,
        product_id,
        len(lines),
        preview["total_estimated_usd"],
        preview["effective_strategy"],
    )

    if preview_log_key not in _LOGGED_PREVIEW_KEYS:
        _LOGGED_PREVIEW_KEYS.add(preview_log_key)
        logger.info(
            "pr_preview_built",
            component="pr_po_pr_service",
            status="success",
            payload={
                "session_id": session_id,
                "run_id": run_id,
                "product_id": product_id,
                "requester_user_id": requester_user_id,
                "line_count": len(lines),
                "total_estimated_usd": preview["total_estimated_usd"],
                "effective_strategy": preview["effective_strategy"],
                "preview_log_deduplicated": True,
            },
        )

    return preview


@traceable_if_enabled(
    name="Create Purchase Requisition",
    run_type="tool",
    tags=["pr-po", "purchase-requisition", "create"],
)
def create_purchase_requisition(
    preview: Dict[str, Any],
) -> Dict[str, Any]:
    """Create an idempotent Purchase Requisition and its line items."""
    started_at = time.perf_counter()

    required_fields = (
        "session_id",
        "run_id",
        "requester_user_id",
        "product_id",
        "lines",
    )
    missing = [
        field
        for field in required_fields
        if not preview.get(field)
    ]

    if missing:
        raise PRServiceError(
            "Missing required PR creation fields: "
            + ", ".join(missing)
        )

    existing = get_existing_pr_for_run(
        preview["session_id"],
        preview["run_id"],
    )

    if existing:
        logger.info(
            "existing_pr_reused",
            component="pr_po_pr_service",
            status="success",
            payload={
                "pr_id": existing["pr_id"],
                "session_id": preview["session_id"],
                "run_id": preview["run_id"],
            },
        )
        return get_purchase_requisition(existing["pr_id"])

    pr_id = _new_pr_id()

    logger.info(
        "pr_creation_started",
        component="pr_po_pr_service",
        status="running",
        payload={
            "pr_id": pr_id,
            "session_id": preview["session_id"],
            "run_id": preview["run_id"],
            "product_id": preview["product_id"],
            "line_count": len(preview["lines"]),
        },
    )

    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO purchase_requisitions (
                    pr_id,
                    requested_by,
                    department,
                    status,
                    total_estimated_usd,
                    required_date,
                    source_session_id,
                    source_run_id,
                    product_id,
                    demand_forecast,
                    effective_strategy
                )
                VALUES (?, ?, ?, 'Pending Approval', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pr_id,
                    preview["requester_user_id"],
                    preview["department"],
                    preview["total_estimated_usd"],
                    preview["required_date"],
                    preview["session_id"],
                    preview["run_id"],
                    preview["product_id"],
                    preview["demand_forecast"],
                    preview["effective_strategy"],
                ),
            )

            for line in preview["lines"]:
                conn.execute(
                    """
                    INSERT INTO pr_lines (
                        pr_id,
                        item_id,
                        quantity,
                        unit,
                        estimated_unit_cost_usd,
                        notes,
                        supplier_id,
                        supplier_name,
                        procurement_strategy,
                        lead_time_days,
                        estimated_delivery_date,
                        line_total_usd,
                        reasoning_snapshot
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pr_id,
                        line["item_id"],
                        line["quantity"],
                        line["unit"],
                        line["estimated_unit_cost_usd"],
                        line["item_name"],
                        line["supplier_id"],
                        line["supplier_name"],
                        line["procurement_strategy"],
                        line["lead_time_days"],
                        line["estimated_delivery_date"],
                        line["line_total_usd"],
                        line["reasoning_snapshot"],
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
                VALUES (?, 'pr_created', ?, ?)
                """,
                (
                    pr_id,
                    preview["requester_user_id"],
                    json.dumps(
                        {
                            "session_id": preview["session_id"],
                            "run_id": preview["run_id"],
                            "line_count": len(preview["lines"]),
                        }
                    ),
                ),
            )
            conn.commit()

    except Exception as exc:
        logger.exception(
            "pr_creation_failed",
            error=exc,
            component="pr_po_pr_service",
            status="failed",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            payload={
                "pr_id": pr_id,
                "session_id": preview["session_id"],
                "run_id": preview["run_id"],
            },
        )
        raise PRServiceError(
            "Purchase Requisition creation failed."
        ) from exc

    result = get_purchase_requisition(pr_id)

    logger.info(
        "pr_creation_completed",
        component="pr_po_pr_service",
        status="success",
        duration_ms=(time.perf_counter() - started_at) * 1000,
        payload={
            "pr_id": pr_id,
            "status": result["status"],
            "line_count": len(result["lines"]),
            "total_estimated_usd": float(
                result.get("total_estimated_usd") or 0
            ),
        },
    )

    return result


def list_purchase_requisitions(
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List PR headers, optionally filtered by status."""
    query = """
        SELECT
            pr.*,
            u.name AS requester_name
        FROM purchase_requisitions pr
        LEFT JOIN users u
          ON u.user_id = pr.requested_by
    """
    params: List[Any] = []

    if status and status != "All":
        query += " WHERE pr.status = ?"
        params.append(status)

    query += " ORDER BY pr.created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


def get_purchase_requisition(
    pr_id: str,
) -> Dict[str, Any]:
    """Load one PR header with requester, approver, and line details."""
    with get_connection() as conn:
        header = conn.execute(
            """
            SELECT
                pr.*,
                req.name AS requester_name,
                app.name AS approver_name
            FROM purchase_requisitions pr
            LEFT JOIN users req
              ON req.user_id = pr.requested_by
            LEFT JOIN users app
              ON app.user_id = pr.approved_by
            WHERE pr.pr_id = ?
            """,
            (pr_id,),
        ).fetchone()

        if not header:
            raise PRServiceError(
                "Purchase Requisition was not found."
            )

        lines = conn.execute(
            """
            SELECT *
            FROM pr_lines
            WHERE pr_id = ?
            ORDER BY pr_line_id
            """,
            (pr_id,),
        ).fetchall()

    result = dict(header)
    result["lines"] = [dict(row) for row in lines]
    return result
