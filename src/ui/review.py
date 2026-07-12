from __future__ import annotations

import json
from typing import Any, Dict, Optional

import streamlit as st

from persistence import (
    load_latest_review_decision,
    load_session_activity,
    save_decision_override,
    save_message,
    save_session_activity,
)
from decision_review import build_effective_procurement_plan
from ui.utils import (
    format_money,
    format_optional_days,
    get_procurement_plan,
    humanize_label,
)


def reasoning_branch_has_items(final_state: Optional[Dict[str, Any]], branch_key: str) -> bool:
    if not final_state:
        return False
    branch = final_state.get(branch_key)
    if not isinstance(branch, dict):
        return False
    items = branch.get("items")
    return isinstance(items, list) and len(items) > 0


def build_strategy_options(final_state: Optional[Dict[str, Any]]) -> list[str]:
    has_contracted = reasoning_branch_has_items(final_state, "contracted_reasoning")
    has_spot = reasoning_branch_has_items(final_state, "spot_reasoning")

    options = ["no_override"]
    if has_contracted:
        options.append("contracted_procurement")
    if has_spot:
        options.append("spot_procurement")
    if has_contracted and has_spot:
        options.append("hybrid_procurement")
    options.append("defer_procurement")
    return list(dict.fromkeys(options))


def get_available_suppliers_for_item(final_state: Optional[Dict[str, Any]], item_id: str) -> list[str]:
    if not final_state:
        return []
    supplier_intel = final_state.get("supplier_intelligence_output") or {}
    for item in supplier_intel.get("items_analyzed", []) or []:
        if item.get("item_id") != item_id:
            continue
        return [
            supplier.get("supplier_name") or supplier.get("name")
            for supplier in item.get("suppliers", []) or []
            if supplier.get("supplier_name") or supplier.get("name")
        ]
    return []


def render_available_strategy_explanation(final_state: Optional[Dict[str, Any]]) -> None:
    has_contracted = reasoning_branch_has_items(final_state, "contracted_reasoning")
    has_spot = reasoning_branch_has_items(final_state, "spot_reasoning")

    if has_contracted and has_spot:
        st.caption(
            "Both Contracted and Spot reasoning are available for this run. Hybrid Procurement is enabled because both branches were evaluated."
        )
    elif has_contracted:
        st.caption(
            "Only Contracted reasoning is available for this run. Spot and Hybrid options are hidden because the supervisor did not execute spot reasoning."
        )
    elif has_spot:
        st.caption(
            "Only Spot reasoning is available for this run. Contracted and Hybrid options are hidden because contracted reasoning is not available."
        )
    else:
        st.caption(
            "No strategy reasoning branch is available. You can only approve the saved recommendation or defer."
        )


def render_effective_plan_preview(effective_decision: Dict[str, Any]) -> None:
    st.subheader("Effective Procurement Plan Preview")
    human_decision = effective_decision.get("human_decision", {})
    metrics = effective_decision.get("effective_metrics", {})
    plan = effective_decision.get("effective_plan", [])

    cols = st.columns(4)
    cols[0].metric("Final Strategy", humanize_label(human_decision.get("final_strategy")))
    cols[1].metric("Approval Status", humanize_label(human_decision.get("approval_status")))
    cols[2].metric("Critical Path", format_optional_days(metrics.get("critical_path_days")))
    cols[3].metric("Total Cost", format_money(metrics.get("total_procurement_cost")))

    if not plan:
        if human_decision.get("approval_status") == "deferred":
            st.warning("Procurement has been deferred. No PR will be created from this review decision.")
        else:
            st.warning("No procurement plan will be executed for this review decision.")
        return

    rows = []
    for item in plan:
        rows.append({
            "Item": f"{item.get('item_id')} | {item.get('item_name')}",
            "Strategy": humanize_label(item.get("strategy")),
            "Supplier": item.get("selected_supplier_name"),
            "Qty": item.get("order_quantity"),
            "Lead Time": item.get("lead_time_days"),
            "Cost": item.get("total_cost"),
            "Source": item.get("source"),
        })
    st.dataframe(rows, width="stretch", hide_index=True)


def _strategy_key(session_id: str, run_id: Optional[str]) -> str:
    return f"review_strategy_{session_id}_{run_id}"


def _reason_key(session_id: str, run_id: Optional[str]) -> str:
    return f"review_reason_{session_id}_{run_id}"


def _supplier_key(session_id: str, run_id: Optional[str], item_id: str) -> str:
    return f"supplier_override_{session_id}_{run_id}_{item_id}"


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


def _normalize_saved_review(
    saved_review: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Normalize review data loaded either from session state or persistence.

    Older persistence records may store supplier overrides and the effective
    decision inside metadata, while the current UI session stores them at the
    top level.
    """
    if not saved_review:
        return {}

    metadata = _as_dict(saved_review.get("metadata"))
    details = _as_dict(saved_review.get("details"))

    effective_decision = _as_dict(
        saved_review.get("effective_decision")
        or metadata.get("effective_decision")
        or metadata.get("effective_plan")
        or details.get("effective_decision")
    )

    human_decision = _as_dict(
        effective_decision.get("human_decision")
    )

    supplier_overrides = (
        saved_review.get("supplier_overrides")
        or metadata.get("supplier_overrides")
        or details.get("supplier_overrides")
        or human_decision.get("supplier_overrides")
        or {}
    )

    override_strategy = (
        saved_review.get("override_strategy")
        or metadata.get("override_strategy")
        or details.get("override_strategy")
        or human_decision.get("override_strategy")
        or "no_override"
    )

    override_reason = (
        saved_review.get("override_reason")
        or metadata.get("override_reason")
        or details.get("override_reason")
        or human_decision.get("override_reason")
        or ""
    )

    return {
        **saved_review,
        "override_strategy": override_strategy,
        "override_reason": override_reason,
        "supplier_overrides": (
            supplier_overrides
            if isinstance(supplier_overrides, dict)
            else {}
        ),
        "effective_decision": effective_decision,
    }


def _load_saved_review(
    session_id: str,
    run_id: Optional[str],
) -> Dict[str, Any]:
    """
    Load the complete saved review from the activity log first.

    The recommendation activity contains the full effective decision,
    supplier overrides, and requester reason. The decision-overrides table
    remains a fallback for older records.
    """
    for activity in load_session_activity(
        session_id,
        limit=100,
    ):
        if (
            run_id
            and activity.get("run_id") != run_id
        ):
            continue

        if activity.get("action") not in {
            "recommendation_approved",
            "recommendation_override_applied",
        }:
            continue

        details = _as_dict(
            activity.get("details") or {}
        )
        effective_decision = _as_dict(
            details.get("effective_decision")
            or {}
        )

        return _normalize_saved_review({
            "session_id": session_id,
            "run_id": activity.get("run_id"),
            "created_at": activity.get("created_at"),
            "action": activity.get("action"),
            "override_strategy": details.get(
                "override_strategy",
                "no_override",
            ),
            "override_reason": details.get(
                "override_reason",
                "",
            ),
            "supplier_overrides": details.get(
                "supplier_overrides",
                {},
            ),
            "effective_decision": (
                effective_decision
            ),
        })

    return _normalize_saved_review(
        load_latest_review_decision(
            session_id=session_id,
            run_id=run_id,
        )
    )


def _initialize_review_widgets(
    session_id: str,
    run_id: Optional[str],
    strategy_options: list[str],
    procurement_plan: list[Dict[str, Any]],
    final_state: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    token = f"{session_id}:{run_id}"

    expected_widget_keys = {
        _strategy_key(session_id, run_id),
        _reason_key(session_id, run_id),
    }

    for item in procurement_plan:
        item_id = item.get("item_id")
        if item_id:
            expected_widget_keys.add(
                _supplier_key(
                    session_id,
                    run_id,
                    item_id,
                )
            )

    widgets_still_present = all(
        key in st.session_state
        for key in expected_widget_keys
    )

    if (
        st.session_state.get(
            "review_widgets_initialized_for_run"
        )
        == token
        and widgets_still_present
    ):
        return st.session_state.get(
            "saved_review_decision"
        )

    saved_review = st.session_state.get(
        "saved_review_decision"
    )

    if (
        not saved_review
        or saved_review.get("run_id") != run_id
    ):
        saved_review = _load_saved_review(
            session_id=session_id,
            run_id=run_id,
        )
    else:
        saved_review = _normalize_saved_review(
            saved_review
        )

    st.session_state.saved_review_decision = (
        saved_review or None
    )
    st.session_state.review_state_run_id = (
        run_id
    )

    strategy_key = _strategy_key(
        session_id,
        run_id,
    )
    reason_key = _reason_key(
        session_id,
        run_id,
    )

    saved_strategy = (
        saved_review.get("override_strategy")
        if saved_review
        else "no_override"
    )

    if saved_strategy not in strategy_options:
        saved_strategy = "no_override"

    st.session_state[strategy_key] = (
        saved_strategy
    )
    st.session_state[reason_key] = (
        saved_review.get("override_reason", "")
        if saved_review
        else ""
    )

    saved_supplier_overrides = (
        saved_review.get(
            "supplier_overrides",
            {},
        )
        if saved_review
        else {}
    )

    for item in procurement_plan:
        item_id = item.get("item_id")
        key = _supplier_key(
            session_id,
            run_id,
            item_id,
        )
        suppliers = (
            get_available_suppliers_for_item(
                final_state,
                item_id,
            )
        )
        saved_supplier = (
            saved_supplier_overrides.get(
                item_id
            )
        )

        st.session_state[key] = (
            saved_supplier
            if saved_supplier in suppliers
            else "No supplier override"
        )

    st.session_state[
        "review_widgets_initialized_for_run"
    ] = token

    return saved_review


def render_recommendation_review_controls(
    decision: Dict[str, Any],
    session_id: str,
    run_id: Optional[str],
    final_state: Optional[Dict[str, Any]] = None,
) -> None:
    st.subheader("Review Procurement Recommendation")

    original_strategy = decision.get("recommended_strategy", "unknown")
    procurement_plan = get_procurement_plan(decision)

    st.info(
        "The AI recommendation is preserved for auditability. Any strategy or supplier changes are stored as human overrides and used to build an effective execution plan. No Purchase Requisition is created in this step."
    )

    render_available_strategy_explanation(final_state)
    strategy_options = build_strategy_options(final_state)

    saved_review = _initialize_review_widgets(
        session_id=session_id,
        run_id=run_id,
        strategy_options=strategy_options,
        procurement_plan=procurement_plan,
        final_state=final_state,
    )


    strategy_key = _strategy_key(session_id, run_id)
    reason_key = _reason_key(session_id, run_id)

    override_strategy = st.selectbox(
        "Strategy Decision",
        options=strategy_options,
        format_func=lambda value: "Approve AI Recommendation" if value == "no_override" else humanize_label(value),
        key=strategy_key,
    )

    st.markdown("**Optional Supplier Overrides**")
    supplier_overrides: Dict[str, str] = {}

    if procurement_plan:
        for item in procurement_plan:
            item_id = item.get("item_id")
            item_name = item.get("item_name")
            current_supplier = item.get("selected_supplier_name")
            suppliers = get_available_suppliers_for_item(final_state, item_id)
            if not suppliers:
                continue

            options = ["No supplier override"] + suppliers
            label = f"{item_id} | {item_name} — current: {current_supplier}"
            key = _supplier_key(session_id, run_id, item_id)

            selected = st.selectbox(label, options=options, key=key)
            if selected != "No supplier override":
                supplier_overrides[item_id] = selected

    override_reason = st.text_area(
        "Review / Override Reason",
        placeholder="Required for strategy or supplier overrides. Optional when approving the AI recommendation.",
        key=reason_key,
    )

    effective_preview = build_effective_procurement_plan(
        decision=decision,
        final_state=final_state or {},
        override_strategy=override_strategy,
        supplier_overrides=supplier_overrides,
        override_reason=override_reason or None,
        reviewer="streamlit_user",
    )

    render_effective_plan_preview(effective_preview)

    if saved_review:
        st.caption(f"Loaded saved review from {saved_review.get('created_at') or 'the previous session'}.")

    col1, col2 = st.columns(2)
    with col1:
        submit_review = st.button(
            "Save Review Decision",
            type="primary",
            key=f"save_review_{session_id}_{run_id}",
        )
    with col2:
        st.caption("Saving updates the effective decision used for PR creation.")

    if not submit_review:
        return

    has_override = override_strategy != "no_override" or bool(supplier_overrides)
    if has_override and not override_reason.strip():
        st.error("Please provide a reason for strategy or supplier override.")
        return

    if has_override:
        save_decision_override(
            session_id=session_id,
            run_id=run_id,
            original_strategy=original_strategy,
            override_strategy=override_strategy,
            override_reason=override_reason,
            metadata={
                "source": "streamlit_ui",
                "supplier_overrides": supplier_overrides,
                "effective_plan": effective_preview,
                "available_strategy_options": strategy_options,
            },
        )

    action = "recommendation_override_applied" if has_override else "recommendation_approved"

    save_session_activity(
        session_id=session_id,
        run_id=run_id,
        actor="user",
        action=action,
        entity_type="procurement_recommendation",
        entity_id=run_id,
        details={
            "original_strategy": original_strategy,
            "override_strategy": override_strategy,
            "override_reason": override_reason or "",
            "supplier_overrides": supplier_overrides,
            "available_strategy_options": strategy_options,
            "effective_decision": effective_preview,
            "note": "Review decision saved. No PR has been created yet.",
        },
    )

    save_message(
        session_id=session_id,
        role="assistant",
        content=(
            "Review saved. Final strategy: "
            f"{humanize_label(effective_preview['human_decision']['final_strategy'])}. "
            "No Purchase Requisition has been created yet."
        ),
        metadata={
            "action": action,
            "pr_created": False,
            "effective_decision": effective_preview,
        },
    )

    st.session_state.saved_review_decision = {
        "session_id": session_id,
        "run_id": run_id,
        "action": action,
        "override_strategy": override_strategy,
        "supplier_overrides": supplier_overrides,
        "override_reason": override_reason or "",
        "effective_decision": effective_preview,
    }
    st.session_state.review_state_run_id = run_id
    st.session_state[
        "review_widgets_initialized_for_run"
    ] = f"{session_id}:{run_id}"

    # Keep the current widget values visible after saving. A later session
    # reload rehydrates from the authoritative recommendation activity.
    st.session_state[
        "review_widgets_initialized_for_run"
    ] = f"{session_id}:{run_id}"

    st.success(
        "Review decision saved. "
        "No PR has been created yet."
    )
