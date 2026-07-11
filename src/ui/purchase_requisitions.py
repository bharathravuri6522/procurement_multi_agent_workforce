from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st

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
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%b %d, %Y %I:%M %p")
    except ValueError:
        return text


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


def _progress_states(status: str) -> List[Dict[str, str]]:
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


def _render_progress_line(status: str) -> None:
    html = ['<div class="pr-progress">']
    for step in _progress_states(status):
        html.append(
            f'<div class="pr-progress-step {step["state"]}"><div class="pr-progress-dot">{step["icon"]}</div><div class="pr-progress-label">{step["label"]}</div></div>'
        )
    html.append('</div>')
    st.markdown(''.join(html), unsafe_allow_html=True)


def _render_pr_card(pr: Dict[str, Any]) -> None:
    requester = pr.get("requester_name") or pr.get("requested_by") or "N/A"
    status = _friendly_status(pr.get("status"))
    badge_class = _status_badge_class(pr.get("status"))
    total = float(pr.get("total_estimated_usd") or 0)
    created = _format_created_at(pr.get("created_at"))

    with st.container(border=True):
        title_col, status_col, action_col = st.columns([4.6, 1.15, 1.25])

        with title_col:
            st.markdown(f"### {pr.get('pr_id')}")

        with status_col:
            st.markdown(
                f"""
                <div style="padding-top: 9px; text-align: center;">
                    <span class="pr-status-badge {badge_class}">{status}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with action_col:
            if st.button(
                "View Details",
                key=f"view_pr_{pr['pr_id']}",
                use_container_width=True,
            ):
                st.session_state[SELECTED_PR_KEY] = pr["pr_id"]
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


def _filter_prs(prs: List[Dict[str, Any]], status_filter: str) -> List[Dict[str, Any]]:
    if status_filter == "All":
        return prs
    if status_filter == "Completed":
        return [pr for pr in prs if pr.get("status") in {"Approved", "PO Created"}]
    return [pr for pr in prs if pr.get("status") == status_filter]


def render_pr_detail(pr_id: str) -> None:
    pr = get_purchase_requisition(pr_id)
    existing_pos = list_purchase_orders_for_pr(pr_id)

    st.divider()
    title_col, close_col = st.columns([5.6, 0.4])

    with title_col:
        st.subheader(pr["pr_id"])

    with close_col:
        if st.button(
            "×",
            key=f"close_pr_details_{pr_id}",
            help="Close details",
            use_container_width=True,
        ):
            st.session_state[SELECTED_PR_KEY] = None
            st.rerun()

    _render_progress_line(pr["status"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", _friendly_status(pr["status"]))
    c2.metric("Total", f"${float(pr['total_estimated_usd'] or 0):,.2f}")
    c3.metric("Requester", pr.get("requester_name") or pr["requested_by"])
    c4.metric("Strategy", str(pr.get("effective_strategy") or "N/A").replace("_", " ").title())

    st.markdown("### PR Lines")
    st.dataframe(
        [{
            "Item": line["item_id"],
            "Supplier": line["supplier_name"],
            "Strategy": line["procurement_strategy"],
            "Qty": line["quantity"],
            "Unit Cost": line["estimated_unit_cost_usd"],
            "Line Total": line["line_total_usd"],
            "Lead Time": line["lead_time_days"],
        } for line in pr["lines"]],
        hide_index=True,
        use_container_width=True,
    )

    supervisor = determine_next_action(pr_id=pr_id, status=pr["status"], has_purchase_orders=bool(existing_pos))
    st.info(f"Supervisor Next Action: {supervisor.next_action.replace('_', ' ').title()} — {supervisor.reason}")

    if supervisor.next_action == "await_approval":
        st.markdown("### Approval")
        approvers = get_eligible_approvers(
            pr_total=float(pr["total_estimated_usd"] or 0),
            requester_user_id=pr["requested_by"],
        )
        if not approvers:
            st.error("No eligible approver is available.")
            return

        approver_map = {
            f"{user['name']} | {user['role']} | Limit ${user['can_approve_up_to_usd']:,.2f}": user
            for user in approvers
        }
        selected_label = st.selectbox("Approver", options=list(approver_map.keys()), key=f"approver_{pr_id}")
        selected = approver_map[selected_label]
        approval_code = st.text_input("Approval Code", type="password", key=f"approval_code_{pr_id}")
        note = st.text_area("Approval / Rejection Note", key=f"approval_note_{pr_id}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Approve PR", type="primary", key=f"approve_{pr_id}", use_container_width=True):
                try:
                    result = approve_pr(
                        pr_id=pr_id,
                        approver_user_id=selected["user_id"],
                        approval_code=approval_code,
                        approval_note=note or None,
                    )
                    po_count = len(result.get("purchase_orders") or [])
                    st.success(f"PR approved. The supervisor created {po_count} supplier-specific Purchase Orders.")
                    st.rerun()
                except ApprovalError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"PR approval succeeded, but automatic PO execution failed: {exc}")
        with col2:
            if st.button("Reject PR", key=f"reject_{pr_id}", use_container_width=True):
                try:
                    reject_pr(
                        pr_id=pr_id,
                        approver_user_id=selected["user_id"],
                        approval_code=approval_code,
                        rejection_reason=note,
                    )
                    st.warning("PR rejected. The supervisor stopped PO generation.")
                    st.rerun()
                except ApprovalError as exc:
                    st.error(str(exc))

    if existing_pos:
        st.markdown("### Purchase Orders")
        st.dataframe(existing_pos, hide_index=True, use_container_width=True)


def render_purchase_requisitions_page() -> None:
    _inject_pr_styles()
    st.title("Purchase Requisitions")

    status_filter = st.selectbox(
        "Status",
        options=["All", "Pending Approval", "Completed", "Rejected"],
        index=0,
        key="purchase_requisition_status_filter",
    )

    all_prs = list_purchase_requisitions("All")
    prs = _filter_prs(all_prs, status_filter)

    if not prs:
        st.info(f"No Purchase Requisitions found for status: {status_filter}.")
        return

    st.caption(f"Showing {len(prs)} Purchase Requisition{'s' if len(prs) != 1 else ''}.")

    for pr in prs:
        _render_pr_card(pr)

    selected_pr_id = st.session_state.get(SELECTED_PR_KEY)
    if selected_pr_id:
        valid_pr_ids = {pr.get("pr_id") for pr in all_prs}
        if selected_pr_id in valid_pr_ids:
            render_pr_detail(selected_pr_id)
        else:
            st.session_state[SELECTED_PR_KEY] = None
