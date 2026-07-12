from __future__ import annotations

import argparse
import sys
from pathlib import Path
from pprint import pprint
from typing import Any, Dict


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
AGENTS_DIR = SRC_DIR / "agents"

for path in (SRC_DIR, AGENTS_DIR):
    path_value = str(path)

    if path_value not in sys.path:
        sys.path.insert(0, path_value)


from agents.supervisor import run_procurement_workflow
from core.observability import (
    build_trace_metadata,
    langsmith_extra,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a ForgeForce procurement workflow from the command line."
        )
    )

    parser.add_argument(
        "--product-id",
        required=True,
        help="Product ID to analyze.",
    )
    parser.add_argument(
        "--quantity",
        required=True,
        type=float,
        help="Production quantity.",
    )
    parser.add_argument(
        "--required-date",
        required=True,
        help="Required date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--session-id",
        help="Optional correlation session ID.",
    )
    parser.add_argument(
        "--run-id",
        help="Optional correlation run ID.",
    )
    parser.add_argument(
        "--full-output",
        action="store_true",
        help="Print the complete decision aggregation object.",
    )

    return parser.parse_args()


def humanize(value: Any) -> str:
    if value is None:
        return "N/A"

    return str(value).replace("_", " ").title()


def print_workflow_summary(
    result: Dict[str, Any],
    product_id: str,
) -> None:
    decision = result.get("decision_aggregation") or {}
    planner = result.get("risk_complexity_plan") or {}
    metrics = decision.get("selected_strategy_metrics") or {}
    plan = decision.get("procurement_plan") or []

    total_cost = metrics.get("total_procurement_cost")
    critical_path = metrics.get("critical_path_days")

    print("\nWorkflow completed successfully.\n")
    print(f"Product: {product_id}")
    print(
        "Selected Route: "
        f"{humanize(planner.get('selected_route'))}"
    )
    print(
        "Recommended Strategy: "
        f"{humanize(decision.get('recommended_strategy'))}"
    )
    print(
        "Confidence: "
        f"{humanize(decision.get('decision_confidence'))}"
    )
    print(
        "Human Review Required: "
        f"{'Yes' if decision.get('human_review_required') else 'No'}"
    )
    print(
        "Critical Path: "
        f"{critical_path} days"
        if critical_path is not None
        else "Critical Path: N/A"
    )
    print(
        "Total Cost: "
        f"${float(total_cost):,.2f}"
        if total_cost is not None
        else "Total Cost: N/A"
    )
    print(f"Items in Plan: {len(plan)}")


def main() -> None:
    args = parse_args()

    metadata = build_trace_metadata(
        session_id=args.session_id,
        run_id=args.run_id,
        product_id=args.product_id,
        demand_forecast=args.quantity,
        required_date=args.required_date,
        component="supervisor",
        execution_mode="cli",
    )

    result = run_procurement_workflow(
        product_id=args.product_id,
        demand_forecast=args.quantity,
        required_date=args.required_date,
        session_id=args.session_id,
        run_id=args.run_id,
        langsmith_extra=langsmith_extra(
            metadata=metadata,
            tags=[
                "forgeforce",
                "procurement",
                "cli",
            ],
        ),
    )

    if args.full_output:
        pprint(result.get("decision_aggregation"))
        return

    print_workflow_summary(
        result=result,
        product_id=args.product_id,
    )


if __name__ == "__main__":
    main()