from __future__ import annotations

from typing import Dict, Any, Optional, Tuple

import streamlit as st

from ui.utils import (
    format_money,
    format_optional_days,
    get_procurement_plan,
    humanize_label,
)


def first_present(data: Dict[str, Any], keys: list[str], default=None):
    for key in keys:
        value = data.get(key)
        if value not in (None, "", "N/A"):
            return value
    return default


def normalize_name(value: Any) -> str:
    return str(value or "").strip().lower()


def build_supplier_lookup(final_state: Optional[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Build lookup by (item_id, supplier_name) from supplier_intelligence_output.

    Why this exists:
    - decision_aggregation contains the user-facing selected plan and reasons.
    - supplier_intelligence_output contains full supplier-level evidence:
      contracted lead time, spot/item lead time, contracted cost, spot cost, MOQ, etc.
    - Alternatives in decision_aggregation may be intentionally slim, so the UI enriches them here.
    """
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}

    if not final_state:
        return lookup

    supplier_intel = final_state.get("supplier_intelligence_output") or {}
    items = supplier_intel.get("items_analyzed") or []

    for item in items:
        item_id = item.get("item_id")
        item_standard_lead_time = (
            item.get("item_standard_lead_time")
            or item.get("item_standard_lead_time_days")
            or item.get("item_lead_time_days")
            or item.get("lead_time_days")
        )

        for supplier in item.get("suppliers", []) or []:
            supplier_name = (
                supplier.get("supplier_name")
                or supplier.get("name")
                or supplier.get("supplier")
            )

            if not item_id or not supplier_name:
                continue

            enriched = dict(supplier)
            enriched["_item_standard_lead_time"] = item_standard_lead_time

            lookup[(str(item_id), normalize_name(supplier_name))] = enriched

    return lookup


def find_supplier_context(
    item: Dict[str, Any],
    alt: Dict[str, Any],
    supplier_lookup: Dict[Tuple[str, str], Dict[str, Any]],
) -> Dict[str, Any]:
    item_id = item.get("item_id")
    supplier_name = first_present(
        alt,
        ["supplier_name", "selected_supplier_name", "name"],
    )

    if not item_id or not supplier_name:
        return {}

    return supplier_lookup.get((str(item_id), normalize_name(supplier_name)), {})


def infer_alternative_lead_time(
    alt: Dict[str, Any],
    item: Dict[str, Any],
    supplier_context: Dict[str, Any],
):
    """
    Prefer explicit alternative lead time.
    Then supplier intelligence lead time.
    Then item-level spot lead time for spot strategy.
    """
    lead_time = first_present(
        alt,
        [
            "lead_time_days",
            "lead_time",
            "current_lead_time",
            "current_lead_time_days",
            "current_expected_lead_time_days",
            "contracted_lead_time_days",
            "spot_lead_time_days",
            "item_standard_lead_time_days",
            "item_standard_lead_time",
            "standard_lead_time_days",
            "standard_lead_time",
            "item_lead_time_days",
            "item_lead_time",
        ],
    )

    if lead_time is not None:
        return lead_time

    if item.get("strategy") == "spot":
        return first_present(
            supplier_context,
            [
                "item_standard_lead_time",
                "item_standard_lead_time_days",
                "_item_standard_lead_time",
                "item_lead_time_days",
                "spot_lead_time_days",
            ],
        ) or first_present(
            item,
            ["item_standard_lead_time_days", "item_standard_lead_time", "lead_time_days"],
        )

    return first_present(
        supplier_context,
        [
            "current_lead_time",
            "current_lead_time_days",
            "current_expected_lead_time",
            "current_expected_lead_time_days",
            "contracted_lead_time_days",
            "lead_time_days",
        ],
    )


def infer_alternative_costs(
    alt: Dict[str, Any],
    item: Dict[str, Any],
    supplier_context: Dict[str, Any],
):
    total_cost = first_present(
        alt,
        [
            "total_cost",
            "cost",
            "total_contracted_cost",
            "contracted_total_cost",
            "total_cost_contracted",
            "total_procurement_cost",
        ],
    )

    spot_cost = first_present(
        alt,
        [
            "spot_total_cost",
            "total_spot_cost",
            "total_cost_spot",
            "spot_cost",
            "total_spot_procurement_cost",
        ],
    )

    if total_cost is None:
        total_cost = first_present(
            supplier_context,
            [
                "total_cost_contracted",
                "contracted_total_cost",
                "total_contracted_cost",
                "total_cost",
            ],
        )

    if spot_cost is None:
        spot_cost = first_present(
            supplier_context,
            [
                "total_cost_spot",
                "spot_total_cost",
                "total_spot_cost",
                "total_spot_procurement_cost",
                "spot_cost",
            ],
        )

    # In the spot reasoning schema, total_cost is often already the spot total.
    if item.get("strategy") == "spot" and spot_cost is None:
        spot_cost = total_cost

    return total_cost, spot_cost


def render_alternatives_considered(
    item: Dict[str, Any],
    supplier_lookup: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
) -> None:
    alternatives = (
        item.get("alternatives_considered")
        or item.get("alternative_suppliers")
        or []
    )

    st.markdown("**Alternatives Considered**")

    if not alternatives:
        st.info("No alternative supplier details were returned for this item.")
        return

    supplier_lookup = supplier_lookup or {}

    for idx, alt in enumerate(alternatives, start=1):
        supplier_name = first_present(
            alt,
            ["supplier_name", "selected_supplier_name", "name"],
            "N/A",
        )

        why_not = first_present(
            alt,
            ["why_not_selected", "reason", "reasoning"],
            "N/A",
        )

        supplier_context = find_supplier_context(item, alt, supplier_lookup)
        total_cost, spot_cost = infer_alternative_costs(alt, item, supplier_context)

        risk_level = first_present(
            alt,
            ["risk_level", "delay_risk_level"],
            first_present(supplier_context, ["risk_level", "delay_risk_level"], "N/A"),
        )

        lead_time = infer_alternative_lead_time(alt, item, supplier_context)

        with st.expander(f"Alternative {idx}: {supplier_name}", expanded=False):
            cols = st.columns(4)
            cols[0].metric("Risk Level", humanize_label(risk_level))
            cols[1].metric("Lead Time", format_optional_days(lead_time))
            cols[2].metric("Total Cost", format_money(total_cost))

            if item.get("strategy") == "spot":
                cols[3].metric("Spot Cost", format_money(spot_cost))
            else:
                cols[3].metric("Spot Cost", "N/A")

            st.markdown("**Why Not Selected**")
            st.write(why_not)

            with st.expander("Debug: raw alternative + enriched supplier context", expanded=False):
                st.markdown("Raw alternative")
                st.json(alt)
                st.markdown("Supplier intelligence context used for enrichment")
                st.json(supplier_context)


def render_procurement_plan(
    decision: Dict[str, Any],
    final_state: Optional[Dict[str, Any]] = None,
) -> None:
    st.subheader("Recommended Procurement Plan")

    plan = get_procurement_plan(decision)
    supplier_lookup = build_supplier_lookup(final_state)

    if not plan:
        st.info("No items require procurement for this decision.")
        with st.expander("Debug: available decision keys"):
            st.write(list(decision.keys()))
        return

    for idx, item in enumerate(plan, start=1):
        title = f"{idx}. {item.get('item_id', 'N/A')} | {item.get('item_name', 'N/A')}"
        with st.expander(title, expanded=True):
            cols = st.columns(4)
            cols[0].metric("Strategy", humanize_label(item.get("strategy", "N/A")))
            cols[1].metric(
                "Supplier",
                item.get("selected_supplier_name") or item.get("selected_supplier") or "N/A",
            )
            cols[2].metric("Order Qty", item.get("order_quantity", "N/A"))
            cols[3].metric("Lead Time", format_optional_days(item.get("lead_time_days")))

            st.caption(f"Supplier ID: {item.get('selected_supplier_id') or item.get('supplier_id') or 'N/A'}")

            cols2 = st.columns(4)
            cols2[0].metric("Gross Requirement", item.get("gross_requirement", "N/A"))
            cols2[1].metric("Procurement Gap incl. Safety Stock", item.get("net_requirement", "N/A"))
            cols2[2].metric("Total Cost", format_money(item.get("total_cost")))
            cols2[3].metric("Overage Qty", item.get("overage_quantity", "N/A"))

            with st.expander("Inventory calculation context", expanded=False):
                inv_rows = [
                    {"Metric": "Current Stock", "Value": item.get("current_stock")},
                    {"Metric": "Reserved Qty", "Value": item.get("reserved_qty")},
                    {"Metric": "On Order Qty", "Value": item.get("on_order_qty")},
                    {"Metric": "Safety Stock", "Value": item.get("safety_stock")},
                ]
                st.dataframe(inv_rows, width="stretch", hide_index=True)

            st.markdown("**Supplier Reasoning**")
            st.write(item.get("reasoning") or item.get("supplier_reasoning") or "No supplier reasoning available.")

            tradeoffs = item.get("key_tradeoffs", [])
            if tradeoffs:
                st.markdown("**Key Tradeoffs**")
                for tradeoff in tradeoffs:
                    st.write(f"- {tradeoff}")

            render_alternatives_considered(item, supplier_lookup=supplier_lookup)
