from __future__ import annotations
from typing import Any, Dict, Optional

def format_money(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)

def format_pct(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return str(value)

def format_optional_days(value: Any) -> str:
    if value in (None, "None", "N/A", ""):
        return "N/A"
    return f"{value} days"

def humanize_label(value: Any) -> str:
    if value is None:
        return "N/A"
    text_value = str(value).strip()
    if not text_value:
        return "N/A"
    replacements = {
        "contracted_procurement": "Contracted Procurement",
        "spot_procurement": "Spot Procurement",
        "hybrid_procurement": "Hybrid Procurement",
        "defer_procurement": "Defer Procurement",
        "no_procurement_required": "No Procurement Required",
        "contracted": "Contracted",
        "spot": "Spot",
        "contracted_only": "Contracted Only",
        "contracted_with_risk_review": "Contracted With Risk Review",
        "contracted_then_spot": "Contracted Then Spot",
        "contracted_then_spot_with_risk_review": "Contracted Then Spot With Risk Review",
        "parallel_strategy_comparison": "Parallel Strategy Comparison",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "unknown": "Unknown",
    }
    if text_value in replacements:
        return replacements[text_value]
    return text_value.replace("_", " ").title()

def get_procurement_plan(decision: Dict[str, Any]) -> list:
    return decision.get("procurement_plan") or decision.get("recommended_procurement_plan") or []

def get_planner_context(decision: Dict[str, Any]) -> Dict[str, Any]:
    return decision.get("planner_context") or decision.get("planner_context_used") or {}

def get_decision_from_run(run: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not run:
        return None
    return run.get("decision_aggregation") or run.get("decision_aggregation_json")

def get_final_state_from_run(run: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not run:
        return None
    return run.get("final_state") or run.get("final_state_json")

def get_strategy_summary(comparison: Dict[str, Any], strategy: str) -> Dict[str, Any]:
    nested = comparison.get(strategy) or {}
    if strategy == "contracted":
        return {
            "available": comparison.get("contracted_available", bool(nested)),
            "feasible": comparison.get("contracted_feasible", nested.get("is_original_date_feasible")),
            "critical_path_days": comparison.get("contracted_critical_path_days", nested.get("critical_path_days")),
            "total_cost": comparison.get("contracted_total_cost", nested.get("total_procurement_cost")),
        }
    if strategy == "spot":
        return {
            "available": comparison.get("spot_available", bool(nested)),
            "feasible": comparison.get("spot_feasible", nested.get("is_original_date_feasible")),
            "critical_path_days": comparison.get("spot_critical_path_days", nested.get("critical_path_days")),
            "total_cost": comparison.get("spot_total_cost", nested.get("total_procurement_cost")),
        }
    return {}
