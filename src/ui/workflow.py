from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import streamlit as st

from persistence import create_procurement_session, save_message, save_workflow_run
from pr_po.db import get_connection


FORM_PRODUCT_KEY = "procurement_form_product_id"
FORM_BATCH_COUNT_KEY = "procurement_form_batch_count"
FORM_REQUIRED_DATE_KEY = "procurement_form_required_date"
FORM_LOADED_SESSION_KEY = "procurement_form_loaded_session_id"


def load_products() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT product_id, name, category, typical_order_qty
            FROM products
            ORDER BY product_id
        """).fetchall()

    products = []
    for row in rows:
        product = dict(row)
        product["typical_order_qty"] = max(
            1, int(product.get("typical_order_qty") or 1)
        )
        products.append(product)
    return products


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass
    return date.today() + timedelta(days=14)


def _derive_batch_count(saved_quantity: Any, typical_order_qty: int) -> int:
    try:
        quantity = float(saved_quantity or 0)
    except (TypeError, ValueError):
        quantity = 0

    if quantity <= 0:
        return 1

    # Round upward so restoration never falls below the saved requirement.
    return max(
        1,
        int((quantity + typical_order_qty - 1) // typical_order_qty),
    )


def initialize_request_form_state(products: List[Dict[str, Any]]) -> None:
    if not products:
        return

    if not st.session_state.get(FORM_PRODUCT_KEY):
        st.session_state[FORM_PRODUCT_KEY] = products[0]["product_id"]

    if not st.session_state.get(FORM_BATCH_COUNT_KEY):
        st.session_state[FORM_BATCH_COUNT_KEY] = 1

    if not st.session_state.get(FORM_REQUIRED_DATE_KEY):
        st.session_state[FORM_REQUIRED_DATE_KEY] = (
            date.today() + timedelta(days=14)
        )

    if FORM_LOADED_SESSION_KEY not in st.session_state:
        st.session_state[FORM_LOADED_SESSION_KEY] = None


def restore_request_form_from_session(
    products: List[Dict[str, Any]],
    session: Optional[Dict[str, Any]],
) -> None:
    if not session:
        return

    session_id = session.get("session_id")
    if st.session_state.get(FORM_LOADED_SESSION_KEY) == session_id:
        return

    product_lookup = {p["product_id"]: p for p in products}
    product_id = session.get("product_id")

    if product_id not in product_lookup:
        product_id = products[0]["product_id"]

    typical_qty = product_lookup[product_id]["typical_order_qty"]

    st.session_state[FORM_PRODUCT_KEY] = product_id
    st.session_state[FORM_BATCH_COUNT_KEY] = _derive_batch_count(
        session.get("demand_forecast"),
        typical_qty,
    )
    st.session_state[FORM_REQUIRED_DATE_KEY] = _parse_date(
        session.get("required_date")
    )
    st.session_state[FORM_LOADED_SESSION_KEY] = session_id


def reset_request_form_for_new_session(
    products: List[Dict[str, Any]],
) -> None:
    st.session_state.selected_session = None
    st.session_state.latest_run = None
    st.session_state.decision_result = None
    st.session_state.workflow_final_state = None
    st.session_state.last_run_metadata = None

    st.session_state[FORM_PRODUCT_KEY] = products[0]["product_id"]
    st.session_state[FORM_BATCH_COUNT_KEY] = 1
    st.session_state[FORM_REQUIRED_DATE_KEY] = (
        date.today() + timedelta(days=14)
    )
    st.session_state[FORM_LOADED_SESSION_KEY] = None


def _handle_product_change() -> None:
    st.session_state[FORM_BATCH_COUNT_KEY] = 1
    st.session_state[FORM_LOADED_SESSION_KEY] = None


def _increment_batch() -> None:
    st.session_state[FORM_BATCH_COUNT_KEY] = (
        int(st.session_state.get(FORM_BATCH_COUNT_KEY, 1)) + 1
    )


def _decrement_batch() -> None:
    current = int(st.session_state.get(FORM_BATCH_COUNT_KEY, 1))
    st.session_state[FORM_BATCH_COUNT_KEY] = max(1, current - 1)


def run_and_save_workflow(
    run_procurement_workflow: Callable[..., Dict[str, Any]],
    session_id: str,
    product_id: str,
    demand_forecast: float,
    required_date: str,
) -> Dict[str, Any]:
    with st.spinner("Running procurement workflow..."):
        final_state = run_procurement_workflow(
            product_id=product_id,
            demand_forecast=demand_forecast,
            required_date=required_date,
        )

        run_meta = save_workflow_run(
            session_id=session_id,
            final_state=final_state,
            input_payload={
                "product_id": product_id,
                "demand_forecast": demand_forecast,
                "required_date": required_date,
            },
        )

        decision = final_state.get("decision_aggregation")

        save_message(
            session_id=session_id,
            role="assistant",
            content=(
                "Workflow completed. Recommended strategy: "
                f"{decision.get('recommended_strategy') if decision else 'N/A'}"
            ),
            metadata={
                "run_id": run_meta.get("run_id"),
                "event": "workflow_completed",
            },
        )

    st.session_state.workflow_final_state = final_state
    st.session_state.decision_result = decision
    st.session_state.last_run_metadata = run_meta
    st.session_state.latest_run = run_meta
    return final_state


def render_saved_request_summary(
    products: List[Dict[str, Any]],
    session: Dict[str, Any],
) -> None:
    product_lookup = {p["product_id"]: p for p in products}
    product = product_lookup.get(session.get("product_id"), {})
    typical_qty = int(product.get("typical_order_qty") or 1)
    quantity = float(session.get("demand_forecast") or 0)
    batches = _derive_batch_count(quantity, typical_qty)

    st.header("Procurement Request")
    st.info(
        "This session already contains a procurement analysis. "
        "The original requirement is preserved for conversation, review, "
        "PR, and PO auditability."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Product",
        session.get("product_id") or "N/A",
        product.get("name"),
    )
    c2.metric("Typical Batch Size", f"{typical_qty} units")
    c3.metric("Production Batches", batches)
    c4.metric("Total Quantity", f"{quantity:g} units")

    st.caption(
        f"{batches} production batch"
        f"{'es' if batches != 1 else ''} × "
        f"{typical_qty} units = {batches * typical_qty} units"
    )
    st.write(f"**Required Date:** {session.get('required_date') or 'N/A'}")

    if st.button(
        "Start New Procurement Request",
        type="primary",
        key=f"start_new_request_{session['session_id']}",
    ):
        reset_request_form_for_new_session(products)
        st.rerun()


def render_new_request_form(
    products: List[Dict[str, Any]],
    run_procurement_workflow: Callable[..., Dict[str, Any]],
) -> None:
    product_lookup = {p["product_id"]: p for p in products}
    product_ids = list(product_lookup.keys())

    current_product_id = st.session_state.get(FORM_PRODUCT_KEY)
    if current_product_id not in product_lookup:
        st.session_state[FORM_PRODUCT_KEY] = product_ids[0]

    st.header("Procurement Request")

    selected_product_id = st.selectbox(
        "Product",
        options=product_ids,
        format_func=lambda product_id: (
            f"{product_id} | "
            f"{product_lookup[product_id].get('name') or 'Unnamed Product'}"
        ),
        key=FORM_PRODUCT_KEY,
        on_change=_handle_product_change,
    )

    product = product_lookup[selected_product_id]
    typical_qty = int(product["typical_order_qty"])
    batch_count = int(st.session_state.get(FORM_BATCH_COUNT_KEY, 1))
    total_quantity = typical_qty * batch_count

    col1, col2, col3, col4 = st.columns([1.5, 0.7, 0.7, 1.5])

    with col1:
        st.metric("Typical Batch Size", f"{typical_qty} units")

    with col2:
        st.button(
            "−",
            key="decrease_production_batch",
            disabled=batch_count <= 1,
            on_click=_decrement_batch,
            use_container_width=True,
        )

    with col3:
        st.button(
            "+",
            key="increase_production_batch",
            on_click=_increment_batch,
            use_container_width=True,
        )

    with col4:
        st.metric("Production Batches", batch_count)

    st.markdown(f"### Total Production Quantity: {total_quantity:,} units")
    st.caption(
        f"{batch_count} production batch"
        f"{'es' if batch_count != 1 else ''} × "
        f"{typical_qty} units = {total_quantity} units"
    )

    required_date = st.date_input(
        "Required Date",
        key=FORM_REQUIRED_DATE_KEY,
        min_value=date.today(),
    )

    if st.button(
        "Run Procurement Analysis",
        type="primary",
        key="run_new_procurement_analysis",
    ):
        try:
            session = create_procurement_session(
                app_user_id=st.session_state.app_user["app_user_id"],
                product_id=selected_product_id,
                demand_forecast=float(total_quantity),
                required_date=required_date.isoformat(),
            )

            st.session_state.selected_session = session
            st.session_state[FORM_LOADED_SESSION_KEY] = session["session_id"]

            save_message(
                session_id=session["session_id"],
                role="user",
                content=(
                    f"Run procurement analysis for product {selected_product_id}, "
                    f"{batch_count} production batch"
                    f"{'es' if batch_count != 1 else ''}, "
                    f"total quantity {total_quantity}, "
                    f"required date {required_date.isoformat()}."
                ),
                metadata={
                    "event": "new_workflow_request",
                    "typical_order_qty": typical_qty,
                    "batch_count": batch_count,
                    "total_quantity": total_quantity,
                },
            )

            run_and_save_workflow(
                run_procurement_workflow=run_procurement_workflow,
                session_id=session["session_id"],
                product_id=selected_product_id,
                demand_forecast=float(total_quantity),
                required_date=required_date.isoformat(),
            )

            st.success("Workflow completed and saved.")
            st.rerun()

        except Exception as exc:
            st.error(f"Workflow failed: {exc}")


def render_procurement_request_form(
    run_procurement_workflow: Callable[..., Dict[str, Any]],
) -> None:
    products = load_products()

    if not products:
        st.error(
            "No products are available. Run the database seed scripts first."
        )
        return

    initialize_request_form_state(products)

    selected_session = st.session_state.get("selected_session")
    restore_request_form_from_session(products, selected_session)

    has_completed_analysis = bool(
        selected_session and st.session_state.get("decision_result")
    )

    if has_completed_analysis:
        render_saved_request_summary(products, selected_session)
        return

    render_new_request_form(products, run_procurement_workflow)
