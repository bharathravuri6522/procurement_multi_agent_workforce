from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from persistence import load_session_activity
from pr_po.db import get_connection
from pr_po.approval_service import (
    ApprovalError,
    approve_pr,
    get_eligible_approvers,
    reject_pr,
)
from pr_po.execution_supervisor import determine_next_action
from pr_po.po_service import list_purchase_orders_for_pr
from pr_po.pr_service import (
    get_purchase_requisition,
    list_purchase_requisitions,
)


SELECTED_PR_KEY = "selected_purchase_requisition_id"


def _friendly_status(status: Optional[str]) -> str:
    mapping = {
        "Pending Approval": "Pending Approval",
        "Approved": "Completed",
        "PO Created": "Completed",
        "Rejected": "Rejected",
    }
    return mapping.get(status or "", status or "Unknown")


def _status_badge_class(status: Optional[str]) -> str:
    friendly = _friendly_status(status)
    if friendly == "Completed":
        return "pr-status-completed"
    if friendly == "Rejected":
        return "pr-status-rejected"
    if friendly == "Pending Approval":
        return "pr-status-pending"
    return "pr-status-unknown"


def _format_created_at(value: Any) -> str:
    if not value:
        return "N/A"

    text = str(value)

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
        return parsed.strftime("%b %d, %Y %I:%M %p")
    except ValueError:
        return text


def _format_money(value: Any) -> str:
    return f"${float(value or 0):,.2f}"


def _humanize(value: Any) -> str:
    return str(value or "N/A").replace("_", " ").title()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

        return decoded if isinstance(decoded, dict) else {}

    return {}


def _supplier_name(item: Dict[str, Any]) -> Optional[str]:
    return (
        item.get("selected_supplier_name")
        or item.get("selected_supplier")
        or item.get("supplier_name")
    )


def _strategy_name(item: Dict[str, Any]) -> Optional[str]:
    return (
        item.get("strategy")
        or item.get("procurement_strategy")
    )


def _index_plan(
    plan: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get("item_id")): item
        for item in plan
        if item.get("item_id")
    }


def _ensure_pr_context(
    pr: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Ensure session_id and run_id are available for review-history lookup.

    Some PR service projections omit these fields even though they are stored
    on purchase_requisitions.
    """
    if pr.get("session_id") and pr.get("run_id"):
        return pr

    pr_id = pr.get("pr_id")
    if not pr_id:
        return pr

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                source_session_id AS session_id,
                source_run_id AS run_id,
                product_id
            FROM purchase_requisitions
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()

    if not row:
        return pr

    resolved = dict(pr)
    resolved.update({
        key: value
        for key, value in dict(row).items()
        if value is not None
    })
    return resolved


def _load_review_snapshot(
    pr: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    pr = _ensure_pr_context(pr)
    session_id = pr.get("session_id")
    run_id = pr.get("run_id")

    if not session_id:
        return None

    activities = load_session_activity(
        session_id,
        limit=100,
    )

    for activity in activities:
        if run_id and activity.get("run_id") != run_id:
            continue

        if activity.get("action") not in {
            "recommendation_approved",
            "recommendation_override_applied",
            "decision_override",
        }:
            continue

        details = _as_dict(
            activity.get("details") or {}
        )
        metadata = _as_dict(
            details.get("metadata") or {}
        )
        effective_decision = _as_dict(
            details.get("effective_decision")
            or details.get("effective_plan")
            or metadata.get("effective_decision")
            or metadata.get("effective_plan")
            or {}
        )

        if effective_decision:
            return {
                "activity": activity,
                "details": details,
                "effective_decision": effective_decision,
            }

    return None


def _decision_context_for_lines(
    pr: Dict[str, Any],
) -> Tuple[
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Any],
    Optional[Dict[str, Any]],
]:
    snapshot = _load_review_snapshot(pr)

    if not snapshot:
        return {}, {}, {}, None

    effective_decision = snapshot["effective_decision"]
    original_recommendation = _as_dict(
        effective_decision.get(
            "original_ai_recommendation"
        )
        or {}
    )
    human_decision = _as_dict(
        effective_decision.get("human_decision")
        or {}
    )

    original_plan = (
        original_recommendation.get(
            "procurement_plan"
        )
        or original_recommendation.get(
            "recommended_procurement_plan"
        )
        or []
    )
    effective_plan = (
        effective_decision.get("effective_plan")
        or []
    )

    return (
        _index_plan(original_plan),
        _index_plan(effective_plan),
        human_decision,
        snapshot,
    )


def _line_decision_source(
    line: Dict[str, Any],
    original_item: Optional[Dict[str, Any]],
    effective_item: Optional[Dict[str, Any]],
) -> str:
    source = str(
        (effective_item or {}).get("source")
        or line.get("source")
        or ""
    ).lower()

    if source.startswith("human_"):
        return "Human Override"

    if not original_item:
        return "AI Recommendation"

    original_supplier = _supplier_name(
        original_item
    )
    final_supplier = (
        line.get("supplier_name")
        or _supplier_name(effective_item or {})
    )

    original_strategy = _strategy_name(
        original_item
    )
    final_strategy = (
        line.get("procurement_strategy")
        or _strategy_name(effective_item or {})
    )

    supplier_changed = (
        bool(original_supplier)
        and bool(final_supplier)
        and original_supplier != final_supplier
    )
    strategy_changed = (
        bool(original_strategy)
        and bool(final_strategy)
        and original_strategy != final_strategy
    )

    return (
        "Human Override"
        if supplier_changed or strategy_changed
        else "AI Recommendation"
    )


def _build_line_rows(
    pr: Dict[str, Any],
    original_by_item: Dict[str, Dict[str, Any]],
    effective_by_item: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for line in pr["lines"]:
        item_id = str(line.get("item_id"))
        original_item = original_by_item.get(
            item_id
        )
        effective_item = effective_by_item.get(
            item_id
        )

        rows.append({
            "Item": item_id,
            "Supplier": line.get("supplier_name"),
            "Strategy": _humanize(
                line.get("procurement_strategy")
            ),
            "Decision Source": (
                _line_decision_source(
                    line,
                    original_item,
                    effective_item,
                )
            ),
            "Qty": line.get("quantity"),
            "Unit Cost": line.get(
                "estimated_unit_cost_usd"
            ),
            "Line Total": line.get(
                "line_total_usd"
            ),
            "Lead Time": line.get(
                "lead_time_days"
            ),
        })

    return rows


def _build_change_records(
    pr: Dict[str, Any],
    original_by_item: Dict[str, Dict[str, Any]],
    effective_by_item: Dict[str, Dict[str, Any]],
    human_decision: Dict[str, Any],
    snapshot: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []

    fallback_reason = (
        human_decision.get("override_reason")
        or "No requester comment was recorded."
    )
    activity = (
        (snapshot or {}).get("activity")
        or {}
    )
    reviewer = (
        human_decision.get("reviewer")
        or activity.get("actor")
        or pr.get("requester_name")
        or pr.get("requested_by")
        or "N/A"
    )
    reviewed_at = (
        activity.get("created_at")
        or activity.get("timestamp")
        or (
            (snapshot or {})
            .get("effective_decision", {})
            .get("created_at")
        )
    )

    for line in pr["lines"]:
        item_id = str(line.get("item_id"))
        original_item = original_by_item.get(
            item_id
        )
        effective_item = effective_by_item.get(
            item_id
        )

        decision_source = (
            _line_decision_source(
                line,
                original_item,
                effective_item,
            )
        )

        if decision_source != "Human Override":
            continue

        original_item = original_item or {}
        effective_item = effective_item or {}

        original_supplier = (
            _supplier_name(original_item)
            or "N/A"
        )
        final_supplier = (
            line.get("supplier_name")
            or _supplier_name(effective_item)
            or "N/A"
        )
        original_strategy = (
            _strategy_name(original_item)
            or "N/A"
        )
        final_strategy = (
            line.get("procurement_strategy")
            or _strategy_name(effective_item)
            or "N/A"
        )

        original_cost = (
            original_item.get("total_cost")
            or original_item.get(
                "line_total_usd"
            )
        )
        final_cost = (
            line.get("line_total_usd")
            if line.get("line_total_usd")
            is not None
            else effective_item.get("total_cost")
        )

        original_lead = (
            original_item.get("lead_time_days")
        )
        final_lead = (
            line.get("lead_time_days")
            if line.get("lead_time_days")
            is not None
            else effective_item.get(
                "lead_time_days"
            )
        )

        changes.append({
            "item_id": item_id,
            "item_name": (
                effective_item.get("item_name")
                or original_item.get("item_name")
                or item_id
            ),
            "original_supplier": original_supplier,
            "final_supplier": final_supplier,
            "original_strategy": original_strategy,
            "final_strategy": final_strategy,
            "original_cost": original_cost,
            "final_cost": final_cost,
            "original_lead": original_lead,
            "final_lead": final_lead,
            "reason": (
                effective_item.get(
                    "human_override_reason"
                )
                or fallback_reason
            ),
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
        })

    return changes


def _render_decision_changes(
    line_rows: List[Dict[str, Any]],
    changes: List[Dict[str, Any]],
    human_decision: Dict[str, Any],
) -> None:
    total_items = len(line_rows)
    override_count = len(changes)
    ai_count = max(
        0,
        total_items - override_count,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Items Reviewed", total_items)
    c2.metric(
        "AI Recommendations Accepted",
        ai_count,
    )
    c3.metric("Human Overrides", override_count)

    if not changes:
        st.success(
            "The requester accepted the AI recommendation "
            "for every PR line."
        )
        return

    override_strategy = (
        human_decision.get("override_strategy")
    )

    if (
        override_strategy
        and override_strategy != "no_override"
    ):
        st.info(
            "A strategy-level human override was applied: "
            f"{_humanize(override_strategy)}."
        )

    for change in changes:
        title = (
            f"{change['item_id']} | "
            f"{change['item_name']} — Human Override"
        )

        with st.expander(
            title,
            expanded=True,
        ):
            supplier_col1, supplier_col2 = (
                st.columns(2)
            )
            supplier_col1.metric(
                "AI Recommended Supplier",
                change["original_supplier"],
            )
            supplier_col2.metric(
                "Final Supplier",
                change["final_supplier"],
            )

            strategy_col1, strategy_col2 = (
                st.columns(2)
            )
            strategy_col1.metric(
                "AI Strategy",
                _humanize(
                    change["original_strategy"]
                ),
            )
            strategy_col2.metric(
                "Final Strategy",
                _humanize(
                    change["final_strategy"]
                ),
            )

            cost_col1, cost_col2 = (
                st.columns(2)
            )
            cost_col1.metric(
                "AI Estimated Cost",
                (
                    _format_money(
                        change["original_cost"]
                    )
                    if change[
                        "original_cost"
                    ]
                    is not None
                    else "N/A"
                ),
            )
            cost_col2.metric(
                "Final Cost",
                (
                    _format_money(
                        change["final_cost"]
                    )
                    if change[
                        "final_cost"
                    ]
                    is not None
                    else "N/A"
                ),
            )

            lead_col1, lead_col2 = (
                st.columns(2)
            )
            lead_col1.metric(
                "AI Lead Time",
                (
                    f"{change['original_lead']} days"
                    if change[
                        "original_lead"
                    ]
                    is not None
                    else "N/A"
                ),
            )
            lead_col2.metric(
                "Final Lead Time",
                (
                    f"{change['final_lead']} days"
                    if change[
                        "final_lead"
                    ]
                    is not None
                    else "N/A"
                ),
            )

            st.markdown("**Requester Comment**")
            st.write(change["reason"])

            st.caption(
                f"Reviewed by: {change['reviewer']} | "
                f"Reviewed at: "
                f"{_format_created_at(change['reviewed_at'])}"
            )


def _inject_pr_styles() -> None:
    st.markdown(
        """
        <style>
        .pr-card {border:1px solid rgba(120,120,120,.22);border-radius:14px;padding:18px 20px;margin-bottom:10px;background:rgba(248,249,251,.75)}
        .pr-card-header {display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:10px}
        .pr-card-title {font-size:1.05rem;font-weight:700;color:inherit}
        .pr-card-meta {color:rgba(90,90,90,.9);font-size:.9rem;line-height:1.55}
        .pr-status-badge {display:inline-block;padding:5px 11px;border-radius:999px;font-size:.8rem;font-weight:650;white-space:nowrap}
        .pr-status-completed {background:rgba(38,166,91,.14);color:rgb(24,122,66)}
        .pr-status-rejected {background:rgba(220,53,69,.13);color:rgb(175,36,51)}
        .pr-status-pending {background:rgba(255,193,7,.18);color:rgb(145,101,0)}
        .pr-status-unknown {background:rgba(108,117,125,.14);color:rgb(80,87,94)}
        .pr-progress {display:flex;align-items:flex-start;width:100%;margin:18px 0 28px 0}
        .pr-progress-step {flex:1;position:relative;text-align:center;min-width:0}
        .pr-progress-step:not(:last-child)::after {content:"";position:absolute;top:16px;left:calc(50% + 18px);right:calc(-50% + 18px);height:3px;background:#d9dde4;z-index:0}
        .pr-progress-step.completed:not(:last-child)::after {background:#27ae60}
        .pr-progress-step.rejected:not(:last-child)::after {background:#dc3545}
        .pr-progress-dot {width:34px;height:34px;border-radius:50%;margin:0 auto 8px;display:flex;justify-content:center;align-items:center;position:relative;z-index:1;font-size:18px;font-weight:700;border:3px solid #d9dde4;background:white;color:#8b919a}
        .pr-progress-step.completed .pr-progress-dot {border-color:#27ae60;background:#27ae60;color:white}
        .pr-progress-step.active .pr-progress-dot {border-color:#f0ad00;background:white;color:#b57a00}
        .pr-progress-step.rejected .pr-progress-dot {border-color:#dc3545;background:#dc3545;color:white}
        .pr-progress-label {font-size:.86rem;font-weight:600;line-height:1.25;color:rgba(45,45,45,.92);overflow-wrap:anywhere}
        @media (max-width:900px){.pr-progress-label{font-size:.72rem}.pr-progress-dot{width:29px;height:29px;font-size:15px}.pr-progress-step:not(:last-child)::after{top:14px;left:calc(50% + 15px);right:calc(-50% + 15px)}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _progress_states(
    status: str,
) -> List[Dict[str, str]]:
    if status == "PO Created":
        return [
            {"label": "Recommendation Reviewed", "state": "completed", "icon": "✓"},
            {"label": "PR Created", "state": "completed", "icon": "✓"},
            {"label": "PR Approved", "state": "completed", "icon": "✓"},
            {"label": "Purchase Orders Created", "state": "completed", "icon": "✓"},
        ]

    if status == "Approved":
        return [
            {"label": "Recommendation Reviewed", "state": "completed", "icon": "✓"},
            {"label": "PR Created", "state": "completed", "icon": "✓"},
            {"label": "PR Approved", "state": "completed", "icon": "✓"},
            {"label": "Creating Purchase Orders", "state": "active", "icon": "•"},
        ]

    if status == "Rejected":
        return [
            {"label": "Recommendation Reviewed", "state": "completed", "icon": "✓"},
            {"label": "PR Created", "state": "completed", "icon": "✓"},
            {"label": "PR Rejected", "state": "rejected", "icon": "×"},
            {"label": "Purchase Orders Not Created", "state": "", "icon": "○"},
        ]

    return [
        {"label": "Recommendation Reviewed", "state": "completed", "icon": "✓"},
        {"label": "PR Created", "state": "completed", "icon": "✓"},
        {"label": "Pending Approval", "state": "active", "icon": "•"},
        {"label": "Purchase Orders Created", "state": "", "icon": "○"},
    ]


def _render_progress_line(
    status: str,
) -> None:
    html = ['<div class="pr-progress">']

    for step in _progress_states(status):
        html.append(
            f'<div class="pr-progress-step {step["state"]}">'
            f'<div class="pr-progress-dot">{step["icon"]}</div>'
            f'<div class="pr-progress-label">{step["label"]}</div>'
            "</div>"
        )

    html.append("</div>")

    st.markdown(
        "".join(html),
        unsafe_allow_html=True,
    )


def _render_pr_card(
    pr: Dict[str, Any],
) -> None:
    requester = (
        pr.get("requester_name")
        or pr.get("requested_by")
        or "N/A"
    )
    status = _friendly_status(
        pr.get("status")
    )
    badge_class = _status_badge_class(
        pr.get("status")
    )
    total = float(
        pr.get("total_estimated_usd")
        or 0
    )
    created = _format_created_at(
        pr.get("created_at")
    )

    with st.container(border=True):
        title_col, status_col, action_col = (
            st.columns([4.6, 1.15, 1.25])
        )

        with title_col:
            st.markdown(
                f"### {pr.get('pr_id')}"
            )

        with status_col:
            st.markdown(
                f"""
                <div style="padding-top: 9px; text-align: center;">
                    <span class="pr-status-badge {badge_class}">
                        {status}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with action_col:
            if st.button(
                "View Details",
                key=f"view_pr_{pr['pr_id']}",
                width="stretch",
            ):
                st.session_state[
                    SELECTED_PR_KEY
                ] = pr["pr_id"]
                st.rerun()

        st.markdown(
            f"""
            <div class="pr-card-meta">
                <strong>Total:</strong> ${total:,.2f}<br>
                <strong>Requester:</strong> {requester}<br>
                <strong>Created:</strong> {created}
            </div>
            """,
            unsafe_allow_html=True,
        )


def _filter_prs(
    prs: List[Dict[str, Any]],
    status_filter: str,
) -> List[Dict[str, Any]]:
    if status_filter == "All":
        return prs

    if status_filter == "Completed":
        return [
            pr
            for pr in prs
            if pr.get("status")
            in {"Approved", "PO Created"}
        ]

    return [
        pr
        for pr in prs
        if pr.get("status") == status_filter
    ]


def render_pr_detail(
    pr_id: str,
) -> None:
    pr = _ensure_pr_context(
        get_purchase_requisition(pr_id)
    )
    existing_pos = (
        list_purchase_orders_for_pr(pr_id)
    )

    (
        original_by_item,
        effective_by_item,
        human_decision,
        snapshot,
    ) = _decision_context_for_lines(pr)

    line_rows = _build_line_rows(
        pr,
        original_by_item,
        effective_by_item,
    )
    changes = _build_change_records(
        pr,
        original_by_item,
        effective_by_item,
        human_decision,
        snapshot,
    )

    st.divider()
    title_col, close_col = st.columns(
        [5.6, 0.4]
    )

    with title_col:
        st.subheader(pr["pr_id"])

    with close_col:
        if st.button(
            "×",
            key=f"close_pr_details_{pr_id}",
            help="Close details",
            width="stretch",
        ):
            st.session_state[
                SELECTED_PR_KEY
            ] = None
            st.rerun()

    _render_progress_line(pr["status"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Status",
        _friendly_status(pr["status"]),
    )
    c2.metric(
        "Total",
        _format_money(
            pr.get("total_estimated_usd")
        ),
    )
    c3.metric(
        "Requester",
        pr.get("requester_name")
        or pr["requested_by"],
    )
    c4.metric(
        "Strategy",
        _humanize(
            pr.get("effective_strategy")
        ),
    )

    lines_tab, changes_tab = st.tabs([
        "PR Lines",
        f"Decision Changes ({len(changes)})",
    ])

    with lines_tab:
        st.dataframe(
            line_rows,
            hide_index=True,
            width="stretch",
            column_config={
                "Decision Source": (
                    st.column_config.TextColumn(
                        "Decision Source",
                        help=(
                            "Shows whether the final "
                            "line matches the AI "
                            "recommendation or was "
                            "changed during human review."
                        ),
                    )
                ),
                "Unit Cost": (
                    st.column_config.NumberColumn(
                        "Unit Cost",
                        format="$%.2f",
                    )
                ),
                "Line Total": (
                    st.column_config.NumberColumn(
                        "Line Total",
                        format="$%.2f",
                    )
                ),
                "Lead Time": (
                    st.column_config.NumberColumn(
                        "Lead Time",
                        format="%d days",
                    )
                ),
            },
        )

    with changes_tab:
        _render_decision_changes(
            line_rows,
            changes,
            human_decision,
        )

    supervisor = determine_next_action(
        pr_id=pr_id,
        status=pr["status"],
        has_purchase_orders=bool(
            existing_pos
        ),
    )

    st.info(
        "Supervisor Next Action: "
        f"{_humanize(supervisor.next_action)} — "
        f"{supervisor.reason}"
    )

    if supervisor.next_action == "await_approval":
        st.markdown("### Approval")

        approvers = get_eligible_approvers(
            pr_total=float(
                pr.get(
                    "total_estimated_usd"
                )
                or 0
            ),
            requester_user_id=pr[
                "requested_by"
            ],
        )

        if not approvers:
            st.error(
                "No eligible approver is available."
            )
            return

        approver_map = {
            (
                f"{user['name']} | "
                f"{user['role']} | "
                f"Limit "
                f"${user['can_approve_up_to_usd']:,.2f}"
            ): user
            for user in approvers
        }

        selected_label = st.selectbox(
            "Approver",
            options=list(
                approver_map.keys()
            ),
            key=f"approver_{pr_id}",
        )
        selected = approver_map[
            selected_label
        ]

        approval_code = st.text_input(
            "Approval Code",
            type="password",
            key=f"approval_code_{pr_id}",
        )
        note = st.text_area(
            "Approval / Rejection Note",
            key=f"approval_note_{pr_id}",
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "Approve PR",
                type="primary",
                key=f"approve_{pr_id}",
                width="stretch",
            ):
                try:
                    result = approve_pr(
                        pr_id=pr_id,
                        approver_user_id=selected[
                            "user_id"
                        ],
                        approval_code=(
                            approval_code
                        ),
                        approval_note=(
                            note or None
                        ),
                    )
                    po_count = len(
                        result.get(
                            "purchase_orders"
                        )
                        or []
                    )
                    st.success(
                        "PR approved. The supervisor "
                        f"created {po_count} "
                        "supplier-specific Purchase "
                        "Orders."
                    )
                    st.rerun()
                except ApprovalError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(
                        "PR approval succeeded, but "
                        "automatic PO execution failed: "
                        f"{exc}"
                    )

        with col2:
            if st.button(
                "Reject PR",
                key=f"reject_{pr_id}",
                width="stretch",
            ):
                try:
                    reject_pr(
                        pr_id=pr_id,
                        approver_user_id=selected[
                            "user_id"
                        ],
                        approval_code=(
                            approval_code
                        ),
                        rejection_reason=note,
                    )
                    st.warning(
                        "PR rejected. The supervisor "
                        "stopped PO generation."
                    )
                    st.rerun()
                except ApprovalError as exc:
                    st.error(str(exc))

    if existing_pos:
        st.markdown("### Purchase Orders")
        st.dataframe(
            existing_pos,
            hide_index=True,
            width="stretch",
        )


def render_purchase_requisitions_page() -> None:
    _inject_pr_styles()
    st.title("Purchase Requisitions")

    status_filter = st.selectbox(
        "Status",
        options=[
            "All",
            "Pending Approval",
            "Completed",
            "Rejected",
        ],
        index=0,
        key=(
            "purchase_requisition_status_filter"
        ),
    )

    all_prs = list_purchase_requisitions(
        "All"
    )
    prs = _filter_prs(
        all_prs,
        status_filter,
    )

    if not prs:
        st.info(
            "No Purchase Requisitions found "
            f"for status: {status_filter}."
        )
        return

    st.caption(
        f"Showing {len(prs)} Purchase "
        f"Requisition{'s' if len(prs) != 1 else ''}."
    )

    for pr in prs:
        _render_pr_card(pr)

    selected_pr_id = st.session_state.get(
        SELECTED_PR_KEY
    )

    if selected_pr_id:
        valid_pr_ids = {
            pr.get("pr_id")
            for pr in all_prs
        }

        if selected_pr_id in valid_pr_ids:
            render_pr_detail(
                selected_pr_id
            )
        else:
            st.session_state[
                SELECTED_PR_KEY
            ] = None
