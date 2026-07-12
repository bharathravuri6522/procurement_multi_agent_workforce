from __future__ import annotations

import json
from typing import Any, Dict, Optional

import streamlit as st

from persistence import (
    load_latest_workflow_run,
    load_session_activity,
)

from pr_po.pr_service import (
    PRServiceError,
    build_pr_preview,
    create_purchase_requisition,
    get_existing_pr_for_run,
)
from pr_po.requester_service import ensure_requester_user


def _parse_details(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    return {}


def _load_latest_effective_decision(
    session_id: str,
    run_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    activities = load_session_activity(session_id, limit=100)

    for activity in activities:
        if run_id and activity.get("run_id") not in {None, run_id}:
            continue

        details = _parse_details(activity.get("details"))

        candidates = [
            details.get("effective_decision"),
            details.get("effective_plan"),
            details.get("reviewed_decision"),
            details.get("metadata", {}).get("effective_decision")
            if isinstance(details.get("metadata"), dict)
            else None,
            details,
        ]

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            if candidate.get("effective_plan"):
                return candidate

            if candidate.get("procurement_plan"):
                return {
                    "effective_plan": candidate.get("procurement_plan"),
                    "effective_metrics": (
                        candidate.get("effective_metrics")
                        or candidate.get("selected_strategy_metrics")
                        or {}
                    ),
                    "human_decision": {
                        "final_strategy": (
                            candidate.get("effective_strategy")
                            or candidate.get("recommended_strategy")
                        ),
                        "approval_status": "reviewed",
                    },
                }

    return None


def _fallback_effective_decision_from_run(
    latest_run: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    decision = (
        latest_run.get("decision_aggregation")
        or latest_run.get("decision_aggregation_json")
        or {}
    )

    plan = (
        decision.get("procurement_plan")
        or decision.get("recommended_procurement_plan")
        or []
    )

    if not plan:
        return None

    return {
        "effective_plan": plan,
        "effective_metrics": (
            decision.get("selected_strategy_metrics")
            or {
                "total_procurement_cost": sum(
                    float(item.get("total_cost") or 0)
                    for item in plan
                ),
                "critical_path_days": max(
                    [int(item.get("lead_time_days") or 0) for item in plan]
                    or [0]
                ),
            }
        ),
        "human_decision": {
            "final_strategy": decision.get("recommended_strategy"),
            "approval_status": "reviewed",
            "source": "approved_ai_recommendation",
        },
    }


def _workflow_request_values(
    latest_run: Dict[str, Any],
) -> Dict[str, Any]:
    final_state = (
        latest_run.get("final_state")
        or latest_run.get("final_state_json")
        or {}
    )
    input_payload = (
        latest_run.get("input_payload")
        or latest_run.get("input_payload_json")
        or {}
    )
    decision = (
        latest_run.get("decision_aggregation")
        or latest_run.get("decision_aggregation_json")
        or {}
    )

    return {
        "product_id": (
            input_payload.get("product_id")
            or final_state.get("product_id")
            or decision.get("product_id")
        ),
        "demand_forecast": (
            input_payload.get("demand_forecast")
            or final_state.get("demand_forecast")
        ),
        "required_date": (
            input_payload.get("required_date")
            or final_state.get("required_date")
            or decision.get("required_date")
        ),
    }


def render_pr_creation_panel(session_id: str) -> None:
    latest_run = load_latest_workflow_run(session_id)

    if not latest_run:
        st.info("Complete and save a procurement analysis before creating a PR.")
        return

    run_id = latest_run.get("run_id")

    if not run_id:
        st.warning("The saved workflow does not contain a run ID.")
        return

    st.markdown("---")
    st.subheader("Purchase Requisition")

    existing_pr = get_existing_pr_for_run(
        session_id=session_id,
        run_id=run_id,
    )

    if existing_pr:
        st.success(
            f"Purchase Requisition {existing_pr['pr_id']} already exists "
            f"for this workflow run."
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("PR Number", existing_pr["pr_id"])
        c2.metric("Status", existing_pr["status"])
        c3.metric(
            "Estimated Total",
            f"${float(existing_pr.get('total_estimated_usd') or 0):,.2f}",
        )
        return

    app_user = st.session_state.get("app_user")

    if not app_user:
        st.error("A logged-in application user is required to create a PR.")
        return

    try:
        requester = ensure_requester_user(app_user)
    except ValueError as exc:
        st.error(str(exc))
        return

    effective_decision = _load_latest_effective_decision(
        session_id=session_id,
        run_id=run_id,
    )

    if not effective_decision:
        effective_decision = _fallback_effective_decision_from_run(latest_run)

    if not effective_decision:
        st.info(
            "Review and save the procurement recommendation before creating "
            "a Purchase Requisition."
        )
        return

    request_values = _workflow_request_values(latest_run)

    try:
        preview = build_pr_preview(
            session_id=session_id,
            run_id=run_id,
            requester_user_id=requester["user_id"],
            department=requester.get("department") or "Procurement",
            product_id=request_values.get("product_id") or "N/A",
            demand_forecast=float(
                request_values.get("demand_forecast") or 0
            ),
            required_date=str(
                request_values.get("required_date") or ""
            ),
            effective_decision=effective_decision,
        )
    except PRServiceError as exc:
        st.error(str(exc))
        return

    requester_label = requester.get("name") or requester.get("email")

    st.caption(
        f"Requester: {requester_label} "
        f"({requester.get('email') or 'email unavailable'})"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Product", preview["product_id"])
    c2.metric("Quantity", preview["demand_forecast"])
    c3.metric(
        "Estimated Total",
        f"${float(preview['total_estimated_usd'] or 0):,.2f}",
    )
    c4.metric(
        "Critical Path",
        f"{preview.get('critical_path_days') or 0} days",
    )

    st.dataframe(
        [
            {
                "Item": line["item_id"],
                "Supplier": line["supplier_name"],
                "Strategy": line["procurement_strategy"],
                "Order Qty": line["quantity"],
                "Unit Cost": line["estimated_unit_cost_usd"],
                "Line Total": line["line_total_usd"],
                "Lead Time": line["lead_time_days"],
            }
            for line in preview["lines"]
        ],
        hide_index=True,
        use_container_width=True,
    )

    confirm = st.checkbox(
        "I confirm that the reviewed effective plan should be converted "
        "into a Purchase Requisition.",
        key=f"confirm_create_pr_{session_id}_{run_id}",
    )

    if st.button(
        "Create Purchase Requisition",
        type="primary",
        disabled=not confirm,
        key=f"create_pr_{session_id}_{run_id}",
    ):
        try:
            pr = create_purchase_requisition(preview)
            st.success(
                f"Purchase Requisition {pr['pr_id']} created successfully."
            )
            st.session_state["selected_pr_id"] = pr["pr_id"]
            st.rerun()
        except PRServiceError as exc:
            st.error(str(exc))
