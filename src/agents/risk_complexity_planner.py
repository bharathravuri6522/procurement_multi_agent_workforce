"""
risk_complexity_planner.py
Version: 1.0-deterministic-procurement-complexity

Purpose:
- Compute a deterministic procurement complexity/risk score after Supplier Intelligence.
- Help the Supervisor decide whether a request can use contracted reasoning only,
  or whether spot comparison should also be evaluated.

Design:
- This is NOT an LLM node.
- It uses structured procurement facts already produced by Supplier Intelligence:
  item-level lead time, supplier-specific contracted lead time, inventory shortage,
  supplier count, MOQ overage, capacity, risk, and spot-vs-contracted cost delta.
- The score is explainable and debuggable.

Score dimensions, total 100:
1. Timeline pressure         30
2. Supplier availability     15
3. MOQ / overage impact      15
4. Inventory shortage risk   15
5. Capacity risk             15
6. Supplier performance risk 10

Recommended routes:
- contracted_only: Normal request, no urgent timeline or major constraints.
- contracted_then_spot: Urgent timeline or contracted path likely cannot meet date.
- contracted_then_spot_with_risk_review: Urgent/complex request with capacity/risk issues.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Any, Dict, List, Tuple


PLANNER_VERSION = "risk_complexity_planner | 1.0-deterministic-procurement-complexity"


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "Not available", "N/A"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "Not available", "N/A"):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _days_until(required_date: str | None) -> int:
    if not required_date:
        return 30
    try:
        required = datetime.strptime(required_date, "%Y-%m-%d").date()
        return max(0, (required - date.today()).days)
    except Exception:
        return 30


def _risk_rank(risk_level: Any) -> int:
    risk = str(risk_level or "").strip().lower()
    if risk == "high":
        return 3
    if risk == "medium":
        return 2
    if risk == "low":
        return 1
    return 0


@dataclass
class ItemComplexityBreakdown:
    item_id: str
    item_name: str
    gross_requirement: float
    net_requirement: float
    item_standard_lead_time_days: int
    supplier_count: int
    min_contracted_lead_time_days: int | None
    min_spot_lead_time_days: int | None
    contracted_can_meet_required_date: bool
    spot_can_meet_required_date: bool
    average_overage_pct: float
    max_overage_pct: float
    constrained_supplier_count: int
    high_risk_supplier_count: int
    medium_risk_supplier_count: int
    best_on_time_delivery_pct: float
    worst_quality_rejection_pct: float
    avg_spot_vs_contracted_delta_pct: float
    signals: List[str]


# -----------------------------------------------------------------------------
# Score functions
# -----------------------------------------------------------------------------

def _timeline_score(
    available_days: int,
    min_contracted_lead: int | None,
    item_standard_lead: int | None,
) -> Tuple[int, List[str]]:
    """0-30. Higher means more urgent / less feasible through contracted path."""
    signals: List[str] = []

    if available_days <= 0:
        signals.append("Required date is today or already past.")
        return 30, signals

    # Contracted path is the main concern; spot may recover schedule.
    if min_contracted_lead is None:
        signals.append("No contracted lead-time data available.")
        return 25, signals

    if min_contracted_lead > available_days:
        gap = min_contracted_lead - available_days
        if gap >= 14:
            score = 30
        elif gap >= 7:
            score = 25
        elif gap >= 3:
            score = 20
        else:
            score = 15
        signals.append(
            f"Best contracted lead time exceeds available days by {gap} day(s)."
        )
    else:
        slack = available_days - min_contracted_lead
        if available_days < 14 and slack <= 2:
            score = 15
            signals.append("Contracted path is feasible but has very limited schedule slack.")
        elif available_days < 14:
            score = 10
            signals.append("Urgent request, but contracted path appears feasible.")
        else:
            score = 0

    if item_standard_lead is not None and item_standard_lead <= available_days < min_contracted_lead:
        signals.append("Spot/item-standard lead time may recover the schedule.")

    return score, signals


def _supplier_availability_score(supplier_count: int) -> Tuple[int, List[str]]:
    """0-15. Higher means fewer sourcing options."""
    if supplier_count <= 0:
        return 15, ["No suppliers available for item."]
    if supplier_count == 1:
        return 12, ["Single-source item."]
    if supplier_count == 2:
        return 8, ["Only two suppliers available."]
    if supplier_count <= 4:
        return 4, ["Moderate supplier availability."]
    return 0, []


def _moq_overage_score(suppliers: List[Dict[str, Any]], gross_requirement: float) -> Tuple[int, float, float, List[str]]:
    """0-15. Higher means MOQ creates material excess inventory."""
    signals: List[str] = []
    if not suppliers or gross_requirement <= 0:
        return 0, 0.0, 0.0, signals

    overage_pcts = []
    for sup in suppliers:
        overage = _safe_float(sup.get("overage_quantity"), 0.0)
        overage_pcts.append((overage / gross_requirement) * 100)

    avg_overage = sum(overage_pcts) / len(overage_pcts)
    max_overage = max(overage_pcts)

    if max_overage >= 50 or avg_overage >= 30:
        score = 15
        signals.append("MOQ creates high excess inventory risk.")
    elif max_overage >= 25 or avg_overage >= 15:
        score = 10
        signals.append("MOQ creates moderate excess inventory risk.")
    elif max_overage > 0:
        score = 5
        signals.append("MOQ creates minor excess inventory.")
    else:
        score = 0

    return score, round(avg_overage, 2), round(max_overage, 2), signals


def _inventory_shortage_score(gross_requirement: float, net_requirement: float) -> Tuple[int, List[str]]:
    """0-15. Higher means most/all demand must be procured."""
    if gross_requirement <= 0:
        return 0, []

    shortage_ratio = net_requirement / gross_requirement
    if shortage_ratio >= 1.0:
        return 15, ["Net requirement exceeds or equals gross build requirement after stock/safety checks."]
    if shortage_ratio >= 0.75:
        return 12, ["High inventory shortage relative to build requirement."]
    if shortage_ratio >= 0.5:
        return 8, ["Moderate inventory shortage relative to build requirement."]
    if shortage_ratio > 0:
        return 4, ["Low inventory shortage relative to build requirement."]
    return 0, []


def _capacity_score(suppliers: List[Dict[str, Any]]) -> Tuple[int, int, List[str]]:
    """0-15. Higher means constrained capacity is widespread."""
    if not suppliers:
        return 0, 0, []

    constrained = 0
    for sup in suppliers:
        capacity = str(sup.get("capacity_status") or "").lower()
        if "constrained" in capacity or "limited" in capacity or "tight" in capacity:
            constrained += 1

    ratio = constrained / len(suppliers)
    if ratio >= 0.5:
        return 15, constrained, ["Multiple suppliers show constrained capacity."]
    if constrained >= 1:
        return 8, constrained, ["At least one supplier has constrained capacity."]
    return 0, constrained, []


def _performance_risk_score(suppliers: List[Dict[str, Any]]) -> Tuple[int, int, int, float, float, List[str]]:
    """0-10. Higher means performance/risk metrics are weak."""
    signals: List[str] = []
    if not suppliers:
        return 0, 0, 0, 0.0, 0.0, signals

    high_risk = sum(1 for sup in suppliers if _risk_rank(sup.get("risk_level")) == 3)
    medium_risk = sum(1 for sup in suppliers if _risk_rank(sup.get("risk_level")) == 2)

    on_time_values = [_safe_float(sup.get("on_time_delivery_pct"), 0.0) for sup in suppliers]
    quality_values = [_safe_float(sup.get("quality_rejection_pct"), 0.0) for sup in suppliers]
    best_on_time = max(on_time_values) if on_time_values else 0.0
    worst_quality = max(quality_values) if quality_values else 0.0

    score = 0
    if high_risk:
        score += 6
        signals.append("High-risk supplier option exists.")
    if medium_risk:
        score += 3
        signals.append("Medium-risk supplier option exists.")
    if best_on_time < 90:
        score += 3
        signals.append("Best on-time delivery rate is below 90%.")
    if worst_quality >= 4:
        score += 2
        signals.append("At least one supplier has elevated quality rejection.")

    return min(score, 10), high_risk, medium_risk, round(best_on_time, 2), round(worst_quality, 2), signals


# -----------------------------------------------------------------------------
# Public planner
# -----------------------------------------------------------------------------

def calculate_procurement_complexity(supplier_intelligence_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute procurement complexity from structured supplier intelligence output.

    Returns a plain dict so it can be stored in AgentState and logged easily.
    """
    required_date = supplier_intelligence_output.get("required_date")
    available_days = _days_until(required_date)
    items = supplier_intelligence_output.get("items_analyzed", []) or []

    item_breakdowns: List[ItemComplexityBreakdown] = []
    total_score = 0
    score_by_dimension = {
        "timeline_pressure": 0,
        "supplier_availability": 0,
        "moq_overage_impact": 0,
        "inventory_shortage_risk": 0,
        "capacity_risk": 0,
        "supplier_performance_risk": 0,
    }
    global_signals: List[str] = []

    for item in items:
        suppliers = item.get("suppliers", []) or []
        gross_requirement = _safe_float(item.get("gross_requirement"), 0.0)
        net_requirement = _safe_float(item.get("net_requirement"), 0.0)
        item_standard_lead = _safe_int(item.get("item_standard_lead_time_days"), 0) or None
        supplier_count = len(suppliers)

        contracted_leads = [
            _safe_int(sup.get("current_lead_time"), 0)
            for sup in suppliers
            if _safe_int(sup.get("current_lead_time"), 0) > 0
        ]
        min_contracted_lead = min(contracted_leads) if contracted_leads else None
        min_spot_lead = item_standard_lead

        timeline, timeline_signals = _timeline_score(
            available_days=available_days,
            min_contracted_lead=min_contracted_lead,
            item_standard_lead=item_standard_lead,
        )
        availability, availability_signals = _supplier_availability_score(supplier_count)
        moq, avg_overage, max_overage, moq_signals = _moq_overage_score(suppliers, gross_requirement)
        inventory, inventory_signals = _inventory_shortage_score(gross_requirement, net_requirement)
        capacity, constrained_count, capacity_signals = _capacity_score(suppliers)
        performance, high_risk_count, medium_risk_count, best_on_time, worst_quality, performance_signals = _performance_risk_score(suppliers)

        avg_delta_values = [
            _safe_float(sup.get("spot_vs_contracted_delta_pct"), 0.0)
            for sup in suppliers
        ]
        avg_spot_delta = sum(avg_delta_values) / len(avg_delta_values) if avg_delta_values else 0.0

        item_score = timeline + availability + moq + inventory + capacity + performance
        total_score += item_score

        score_by_dimension["timeline_pressure"] += timeline
        score_by_dimension["supplier_availability"] += availability
        score_by_dimension["moq_overage_impact"] += moq
        score_by_dimension["inventory_shortage_risk"] += inventory
        score_by_dimension["capacity_risk"] += capacity
        score_by_dimension["supplier_performance_risk"] += performance

        signals = timeline_signals + availability_signals + moq_signals + inventory_signals + capacity_signals + performance_signals
        global_signals.extend([f"{item.get('item_id')}: {signal}" for signal in signals])

        item_breakdowns.append(
            ItemComplexityBreakdown(
                item_id=item.get("item_id"),
                item_name=item.get("item_name"),
                gross_requirement=gross_requirement,
                net_requirement=net_requirement,
                item_standard_lead_time_days=item_standard_lead or 0,
                supplier_count=supplier_count,
                min_contracted_lead_time_days=min_contracted_lead,
                min_spot_lead_time_days=min_spot_lead,
                contracted_can_meet_required_date=(min_contracted_lead is not None and min_contracted_lead <= available_days),
                spot_can_meet_required_date=(min_spot_lead is not None and min_spot_lead <= available_days),
                average_overage_pct=avg_overage,
                max_overage_pct=max_overage,
                constrained_supplier_count=constrained_count,
                high_risk_supplier_count=high_risk_count,
                medium_risk_supplier_count=medium_risk_count,
                best_on_time_delivery_pct=best_on_time,
                worst_quality_rejection_pct=worst_quality,
                avg_spot_vs_contracted_delta_pct=round(avg_spot_delta, 2),
                signals=signals,
            )
        )

    item_count = len(items) or 1
    normalized_score = round(total_score / item_count, 2)
    normalized_dimensions = {
        key: round(value / item_count, 2)
        for key, value in score_by_dimension.items()
    }

    any_contract_not_feasible = any(not item.contracted_can_meet_required_date for item in item_breakdowns)
    any_spot_feasible = any(item.spot_can_meet_required_date for item in item_breakdowns)
    all_spot_feasible = bool(item_breakdowns) and all(item.spot_can_meet_required_date for item in item_breakdowns)
    any_constrained_capacity = any(item.constrained_supplier_count > 0 for item in item_breakdowns)
    any_high_or_medium_risk = any(
        item.high_risk_supplier_count > 0 or item.medium_risk_supplier_count > 0
        for item in item_breakdowns
    )
    urgent_timeline = available_days < 14

    if normalized_score >= 70:
        complexity_level = "critical"
    elif normalized_score >= 50:
        complexity_level = "high"
    elif normalized_score >= 30:
        complexity_level = "medium"
    else:
        complexity_level = "low"

    # Route selection. This is still deterministic.
    if urgent_timeline and (any_contract_not_feasible or all_spot_feasible):
        if any_constrained_capacity or any_high_or_medium_risk or normalized_score >= 50:
            selected_route = "contracted_then_spot_with_risk_review"
            route_reason = (
                "Urgent timeline with contracted-path feasibility issue and capacity/risk complexity. "
                "Run contracted and spot reasoning, then include risk review in final decision."
            )
        else:
            selected_route = "contracted_then_spot"
            route_reason = (
                "Urgent timeline and contracted path may miss the deadline. "
                "Run spot comparison for timeline recovery."
            )
    elif any_contract_not_feasible and any_spot_feasible:
        selected_route = "contracted_then_spot"
        route_reason = "Contracted path appears infeasible for at least one item, while spot may recover schedule."
    elif any_constrained_capacity or any_high_or_medium_risk or normalized_score >= 50:
        selected_route = "contracted_with_risk_review"
        route_reason = "Timeline is not urgent, but supplier capacity/risk complexity requires risk review."
    else:
        selected_route = "contracted_only"
        route_reason = "Contracted procurement appears sufficient based on timeline, risk, inventory, and supplier context."

    return {
        "planner_version": PLANNER_VERSION,
        "required_date": required_date,
        "available_days": available_days,
        "items_needing_procurement": len(items),
        "complexity_score": normalized_score,
        "complexity_level": complexity_level,
        "score_by_dimension": normalized_dimensions,
        "selected_route": selected_route,
        "route_reason": route_reason,
        "routing_flags": {
            "urgent_timeline_less_than_14_days": urgent_timeline,
            "any_contract_not_feasible": any_contract_not_feasible,
            "any_spot_feasible": any_spot_feasible,
            "all_spot_feasible": all_spot_feasible,
            "any_constrained_capacity": any_constrained_capacity,
            "any_high_or_medium_risk": any_high_or_medium_risk,
        },
        "item_breakdowns": [asdict(item) for item in item_breakdowns],
        "top_signals": global_signals[:12],
    }
