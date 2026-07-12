from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from pr_po.db import get_connection


SELECTED_PO_PR_KEY = "selected_purchase_order_pr_id"


def _format_datetime(value: Any) -> str:
    if not value:
        return "N/A"

    text = str(value)

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%b %d, %Y %I:%M %p")
    except ValueError:
        return text


def _format_money(value: Any) -> str:
    return f"${float(value or 0):,.2f}"


def _inject_po_styles() -> None:
    st.markdown(
        """
        <style>
        .po-status-badge {
            display: inline-block;
            padding: 5px 11px;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 650;
            white-space: nowrap;
            background: rgba(38, 166, 91, 0.14);
            color: rgb(24, 122, 66);
        }

        .po-card-meta {
            color: rgba(90, 90, 90, 0.92);
            font-size: 0.92rem;
            line-height: 1.6;
        }

        .po-detail-card {
            border: 1px solid rgba(120, 120, 120, 0.22);
            border-radius: 14px;
            padding: 18px 20px;
            margin-bottom: 14px;
            background: rgba(248, 249, 251, 0.68);
        }

        .po-detail-title {
            font-size: 1.02rem;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .po-detail-subtitle {
            color: rgba(90, 90, 90, 0.92);
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def list_po_groups_by_pr() -> List[Dict[str, Any]]:
    """
    Return one row per PR that has generated Purchase Orders.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                pr.pr_id,
                pr.product_id,
                pr.requested_by,
                requester.name AS requester_name,
                pr.approved_by,
                approver.name AS approver_name,
                pr.status AS pr_status,
                pr.created_at AS pr_created_at,
                pr.approved_at,
                pr.po_created_at,
                COUNT(po.po_id) AS po_count,
                COALESCE(SUM(po.total_usd), 0) AS total_po_value,
                MIN(po.created_at) AS first_po_created_at,
                MAX(po.created_at) AS latest_po_created_at
            FROM purchase_requisitions pr
            INNER JOIN purchase_orders po
                ON po.pr_id = pr.pr_id
            LEFT JOIN users requester
                ON requester.user_id = pr.requested_by
            LEFT JOIN users approver
                ON approver.user_id = pr.approved_by
            GROUP BY
                pr.pr_id,
                pr.product_id,
                pr.requested_by,
                requester.name,
                pr.approved_by,
                approver.name,
                pr.status,
                pr.created_at,
                pr.approved_at,
                pr.po_created_at
            ORDER BY
                COALESCE(pr.po_created_at, MAX(po.created_at)) DESC
        """).fetchall()

    return [dict(row) for row in rows]


def list_purchase_orders_for_pr(pr_id: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                po.*,
                supplier.name AS supplier_name
            FROM purchase_orders po
            LEFT JOIN suppliers supplier
                ON supplier.supplier_id = po.supplier_id
            WHERE po.pr_id = ?
            ORDER BY po.created_at, po.po_id
        """, (pr_id,)).fetchall()

    return [dict(row) for row in rows]


def get_po_lines(po_id: str) -> List[Dict[str, Any]]:
    """
    Enrich PO lines with the item name saved on the corresponding PR line.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                pol.po_line_id,
                pol.po_id,
                pol.item_id,
                COALESCE(prl.notes, pol.item_id) AS item_name,
                pol.quantity,
                pol.unit_cost_usd,
                pol.line_total_usd
            FROM po_lines pol
            INNER JOIN purchase_orders po
                ON po.po_id = pol.po_id
            LEFT JOIN pr_lines prl
                ON prl.pr_id = po.pr_id
               AND prl.item_id = pol.item_id
               AND (
                    prl.supplier_id = po.supplier_id
                    OR prl.supplier_id IS NULL
               )
            WHERE pol.po_id = ?
            ORDER BY pol.po_line_id
        """, (po_id,)).fetchall()

    return [dict(row) for row in rows]


def _render_pr_po_summary_card(group: Dict[str, Any]) -> None:
    requester = (
        group.get("requester_name")
        or group.get("requested_by")
        or "N/A"
    )
    approver = (
        group.get("approver_name")
        or group.get("approved_by")
        or "N/A"
    )
    product_id = group.get("product_id") or "N/A"
    po_count = int(group.get("po_count") or 0)
    total_value = _format_money(group.get("total_po_value"))
    created = _format_datetime(
        group.get("po_created_at")
        or group.get("latest_po_created_at")
    )

    with st.container(border=True):
        title_col, status_col, action_col = st.columns([4.6, 1.15, 1.25])

        with title_col:
            st.markdown(f"### {group['pr_id']}")

        with status_col:
            st.markdown(
                """
                <div style="padding-top: 9px; text-align: center;">
                    <span class="po-status-badge">Completed</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with action_col:
            if st.button(
                "View POs",
                key=f"view_pos_{group['pr_id']}",
                use_container_width=True,
            ):
                st.session_state[SELECTED_PO_PR_KEY] = group["pr_id"]
                st.rerun()

        st.markdown(
            f"""
            <div class="po-card-meta">
                <strong>Product:</strong> {product_id}<br>
                <strong>Requested By:</strong> {requester}<br>
                <strong>Approved By:</strong> {approver}<br>
                <strong>Purchase Orders:</strong> {po_count}<br>
                <strong>Total PO Value:</strong> {total_value}<br>
                <strong>POs Created:</strong> {created}
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_single_po_card(po: Dict[str, Any]) -> None:
    lines = get_po_lines(po["po_id"])
    supplier_name = po.get("supplier_name") or po.get("supplier_id") or "N/A"

    with st.container(border=True):
        title_col, status_col = st.columns([5, 1])

        with title_col:
            st.markdown(f"### {po['po_id']}")
            st.caption(f"Supplier: {supplier_name}")

        with status_col:
            st.markdown(
                f"""
                <div style="padding-top: 9px; text-align: center;">
                    <span class="po-status-badge">{po.get('status') or 'Created'}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        c1, c2, c3 = st.columns(3)
        c1.metric("PO Value", _format_money(po.get("total_usd")))
        c2.metric(
            "Expected Delivery",
            po.get("expected_delivery") or "N/A",
        )
        c3.metric("Items", len(lines))

        if not lines:
            st.info("This Purchase Order does not contain any line items.")
            return

        st.dataframe(
            [
                {
                    "Item": (
                        f"{line.get('item_id')} | "
                        f"{line.get('item_name') or line.get('item_id')}"
                    ),
                    "Quantity": line.get("quantity"),
                    "Unit Cost": line.get("unit_cost_usd"),
                    "Line Total": line.get("line_total_usd"),
                }
                for line in lines
            ],
            hide_index=True,
            use_container_width=True,
        )


def render_po_group_detail(pr_id: str) -> None:
    purchase_orders = list_purchase_orders_for_pr(pr_id)

    st.divider()

    title_col, close_col = st.columns([5.6, 0.4])

    with title_col:
        st.subheader(f"Purchase Orders for {pr_id}")

    with close_col:
        if st.button(
            "×",
            key=f"close_po_details_{pr_id}",
            help="Close Purchase Order details",
            use_container_width=True,
        ):
            st.session_state[SELECTED_PO_PR_KEY] = None
            st.rerun()

    if not purchase_orders:
        st.info("No Purchase Orders were found for this PR.")
        return

    combined_value = sum(
        float(po.get("total_usd") or 0)
        for po in purchase_orders
    )

    c1, c2 = st.columns(2)
    c1.metric("Purchase Orders", len(purchase_orders))
    c2.metric("Combined Value", _format_money(combined_value))

    for po in purchase_orders:
        _render_single_po_card(po)


def render_purchase_orders_page() -> None:
    _inject_po_styles()

    st.title("Purchase Orders")

    groups = list_po_groups_by_pr()

    if not groups:
        st.info("No Purchase Orders have been created.")
        return

    st.caption(
        f"Showing {len(groups)} completed Purchase Requisition"
        f"{'s' if len(groups) != 1 else ''} with generated Purchase Orders."
    )

    for group in groups:
        _render_pr_po_summary_card(group)

    selected_pr_id = st.session_state.get(SELECTED_PO_PR_KEY)

    if selected_pr_id:
        valid_pr_ids = {group["pr_id"] for group in groups}

        if selected_pr_id in valid_pr_ids:
            render_po_group_detail(selected_pr_id)
        else:
            st.session_state[SELECTED_PO_PR_KEY] = None
