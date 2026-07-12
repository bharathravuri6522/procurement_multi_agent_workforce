"""
Supervisor and orchestration graph for ForgeForce Procurement AI.

The supervisor coordinates deterministic analysis and LLM reasoning nodes,
then produces a single aggregated procurement recommendation.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import date
import time
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from agent_state import AgentState
from decision_aggregator import aggregate_procurement_decision
from demand_inventory_analyst import analyze_demand_and_inventory
from reasoning_node import reason_and_recommend
from risk_complexity_planner import calculate_procurement_complexity
from spot_reasoning_node import reason_with_spot_strategy
from supplier_intelligence_agent import recommend_suppliers

from core.exceptions import (
    DecisionAggregationError,
    DemandAnalysisError,
    PlannerError,
    SupplierIntelligenceError,
    SupplierReasoningError,
    WorkflowExecutionError,
)
from core.config import settings
from core.logging import bind_log_context, get_logger, reset_log_context
from core.observability import (
    build_trace_metadata,
    langsmith_extra as build_langsmith_extra,
    traceable_if_enabled,
)
from core.timing import timed

from workflow_logger import (
    log_decision_aggregation,
    log_demand_analysis,
    log_execution_strategy,
    log_product_level_summary,
    log_reasoning_item_recommendations,
    log_risk_complexity_planning,
    log_supplier_intelligence,
)


SUPERVISOR_VERSION = (
    "supervisor_with_decision_aggregator_v6 "
    "| parallel-context-propagation"
)

logger = get_logger("supervisor")


def _run_verbose_log(log_function, *args: Any) -> None:
    """Emit detailed legacy workflow reports only when explicitly enabled."""
    if settings.verbose_workflow_logs:
        log_function(*args)



def _require_state_value(
    state: AgentState,
    key: str,
    *,
    component: str,
) -> Any:
    value = state.get(key)
    if value is None:
        raise WorkflowExecutionError(
            f"Required workflow state is missing: {key}.",
            component=component,
        )
    return value


def _nodes_for_route(selected_route: str) -> List[str]:
    if selected_route in {
        "contracted_then_spot",
        "contracted_then_spot_with_risk_review",
        "parallel_contract_and_spot",
    }:
        return ["contracted_reasoning", "spot_reasoning"]

    if selected_route in {
        "spot_only",
        "spot_only_with_risk_review",
    }:
        return ["spot_reasoning"]

    return ["contracted_reasoning"]


@timed(
    component="demand_analyst",
    event="demand_analysis_completed",
)
def demand_analyst_node(state: AgentState) -> Dict[str, Any]:
    logger.info(
        "demand_analysis_started",
        component="demand_analyst",
        status="running",
        payload={
            "product_id": state.get("product_id"),
            "demand_forecast": state.get("demand_forecast"),
            "required_date": state.get("current_date"),
        },
    )

    try:
        result = analyze_demand_and_inventory(
            product_id=state["product_id"],
            demand_forecast=state.get("demand_forecast", 0),
            required_date=state.get("current_date"),
        )
    except Exception as exc:
        logger.exception(
            "demand_analysis_failed",
            error=exc,
            component="demand_analyst",
            status="failed",
            payload={"product_id": state.get("product_id")},
        )
        raise DemandAnalysisError(
            f"Demand analysis failed for product {state.get('product_id')}.",
            component="demand_analyst",
        ) from exc

    _run_verbose_log(log_demand_analysis, result)

    logger.info(
        "demand_analysis_succeeded",
        component="demand_analyst",
        status="success",
        payload={
            "product_id": state.get("product_id"),
            "items_requiring_procurement": len(
                result.get("items_requiring_procurement", [])
                if isinstance(result, dict)
                else []
            ),
        },
    )

    return {
        "demand_analysis": result,
        "current_agent": "demand_analyst",
        "reasoning_trace": ["Demand and inventory analysis completed."],
    }


@timed(
    component="supplier_intelligence",
    event="supplier_intelligence_completed",
)
def supplier_intelligence_node(state: AgentState) -> Dict[str, Any]:
    demand_analysis = _require_state_value(
        state,
        "demand_analysis",
        component="supplier_intelligence",
    )

    logger.info(
        "supplier_intelligence_started",
        component="supplier_intelligence",
        status="running",
    )

    try:
        result = recommend_suppliers(demand_analysis)
    except Exception as exc:
        logger.exception(
            "supplier_intelligence_failed",
            error=exc,
            component="supplier_intelligence",
            status="failed",
        )
        raise SupplierIntelligenceError(
            "Supplier intelligence failed for the current procurement request.",
            component="supplier_intelligence",
        ) from exc

    _run_verbose_log(log_supplier_intelligence, result)

    analyzed_items = (
        result.get("items_analyzed", [])
        if isinstance(result, dict)
        else []
    )
    supplier_count = sum(
        len(item.get("suppliers", []) or [])
        for item in analyzed_items
        if isinstance(item, dict)
    )

    logger.info(
        "supplier_intelligence_succeeded",
        component="supplier_intelligence",
        status="success",
        payload={
            "item_count": len(analyzed_items),
            "supplier_option_count": supplier_count,
        },
    )

    return {
        "supplier_intelligence_output": result,
        "current_agent": "supplier_intelligence",
        "reasoning_trace": [
            "Supplier intelligence and deterministic cost calculations completed."
        ],
    }


@timed(
    component="risk_complexity_planner",
    event="risk_complexity_planning_completed",
)
def risk_complexity_planner_node(state: AgentState) -> Dict[str, Any]:
    supplier_intelligence = _require_state_value(
        state,
        "supplier_intelligence_output",
        component="risk_complexity_planner",
    )

    logger.info(
        "risk_complexity_planning_started",
        component="risk_complexity_planner",
        status="running",
    )

    try:
        plan = calculate_procurement_complexity(supplier_intelligence)
    except Exception as exc:
        logger.exception(
            "risk_complexity_planning_failed",
            error=exc,
            component="risk_complexity_planner",
            status="failed",
        )
        raise PlannerError(
            "The procurement planner could not determine an execution route.",
            component="risk_complexity_planner",
        ) from exc

    selected_route = plan.get("selected_route", "contracted_only")
    nodes_to_run = _nodes_for_route(selected_route)
    plan["execution_nodes"] = nodes_to_run

    _run_verbose_log(log_risk_complexity_planning, plan)
    _run_verbose_log(log_execution_strategy, plan, nodes_to_run)

    logger.info(
        "route_selected",
        component="risk_complexity_planner",
        status="success",
        payload={
            "selected_route": selected_route,
            "complexity_score": plan.get("complexity_score"),
            "complexity_level": plan.get("complexity_level"),
            "execution_nodes": nodes_to_run,
            "route_reason": plan.get("route_reason"),
        },
    )

    return {
        "risk_complexity_plan": plan,
        "next_step": ",".join(nodes_to_run),
        "current_agent": "risk_complexity_planner",
        "reasoning_trace": [
            (
                "Risk and complexity planner selected route "
                f"'{selected_route}' with execution nodes {nodes_to_run}."
            )
        ],
    }


def _run_contracted_reasoning(
    supplier_intelligence: Dict[str, Any],
) -> Dict[str, Any]:
    result = reason_and_recommend(supplier_intelligence)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _run_spot_reasoning(
    supplier_intelligence: Dict[str, Any],
) -> Dict[str, Any]:
    result = reason_with_spot_strategy(supplier_intelligence)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _log_reasoning_result(
    strategy: str,
    result: Dict[str, Any],
) -> None:
    title = (
        "Contracted Product-Level Summary"
        if strategy == "contracted_reasoning"
        else "Spot Product-Level Summary"
    )
    label = "Contracted" if strategy == "contracted_reasoning" else "Spot"

    _run_verbose_log(log_product_level_summary, result, title)
    _run_verbose_log(log_reasoning_item_recommendations, result, label)


@timed(
    component="strategy_reasoning_executor",
    event="strategy_reasoning_completed",
)
def strategy_reasoning_executor_node(state: AgentState) -> Dict[str, Any]:
    supplier_intelligence = _require_state_value(
        state,
        "supplier_intelligence_output",
        component="strategy_reasoning_executor",
    )

    requested_nodes = str(
        state.get("next_step") or "contracted_reasoning"
    ).split(",")

    nodes_to_run = [
        node.strip()
        for node in requested_nodes
        if node.strip() in {"contracted_reasoning", "spot_reasoning"}
    ]

    if not nodes_to_run:
        nodes_to_run = ["contracted_reasoning"]

    logger.info(
        "strategy_reasoning_started",
        component="strategy_reasoning_executor",
        status="running",
        payload={
            "execution_mode": "parallel" if len(nodes_to_run) > 1 else "single",
            "strategies": nodes_to_run,
        },
    )

    updates: Dict[str, Any] = {
        "current_agent": "strategy_reasoning_executor",
        "reasoning_trace": [],
    }

    runners = {
        "contracted_reasoning": _run_contracted_reasoning,
        "spot_reasoning": _run_spot_reasoning,
    }

    try:
        if len(nodes_to_run) == 1:
            strategy = nodes_to_run[0]
            logger.info(
                "reasoning_branch_started",
                component=strategy,
                status="running",
            )
            result = runners[strategy](supplier_intelligence)
            _log_reasoning_result(strategy, result)
            updates[strategy] = result
            updates["reasoning_trace"].append(
                f"{strategy.replace('_', ' ').title()} completed."
            )
            logger.info(
                "reasoning_branch_completed",
                component=strategy,
                status="success",
                payload={"item_count": len(result.get("items", []) or [])},
            )
            return updates

        futures = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            for strategy in nodes_to_run:
                logger.info(
                    "reasoning_branch_started",
                    component=strategy,
                    status="running",
                    payload={"execution_mode": "parallel"},
                )
                worker_context = copy_context()

                futures[
                    executor.submit(
                        worker_context.run,
                        runners[strategy],
                        supplier_intelligence,
                    )
                ] = strategy

            for future in as_completed(futures):
                strategy = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logger.exception(
                        "reasoning_branch_failed",
                        error=exc,
                        component=strategy,
                        status="failed",
                    )
                    raise

                _log_reasoning_result(strategy, result)
                updates[strategy] = result
                updates["reasoning_trace"].append(
                    f"{strategy.replace('_', ' ').title()} completed."
                )
                logger.info(
                    "reasoning_branch_completed",
                    component=strategy,
                    status="success",
                    payload={
                        "execution_mode": "parallel",
                        "item_count": len(result.get("items", []) or []),
                    },
                )

    except Exception as exc:
        logger.exception(
            "strategy_reasoning_failed",
            error=exc,
            component="strategy_reasoning_executor",
            status="failed",
            payload={"strategies": nodes_to_run},
        )
        raise SupplierReasoningError(
            "The selected procurement reasoning strategies could not be completed.",
            component="strategy_reasoning_executor",
        ) from exc

    return updates


@timed(
    component="decision_aggregator",
    event="decision_aggregation_completed",
)
def decision_aggregator_node(state: AgentState) -> Dict[str, Any]:
    logger.info(
        "decision_aggregation_started",
        component="decision_aggregator",
        status="running",
    )

    try:
        result = aggregate_procurement_decision(state)
    except Exception as exc:
        logger.exception(
            "decision_aggregation_failed",
            error=exc,
            component="decision_aggregator",
            status="failed",
        )
        raise DecisionAggregationError(
            "The final procurement recommendation could not be generated.",
            component="decision_aggregator",
        ) from exc

    _run_verbose_log(log_decision_aggregation, result)

    logger.info(
        "decision_aggregation_succeeded",
        component="decision_aggregator",
        status="success",
        payload={
            "recommended_strategy": result.get("recommended_strategy"),
            "decision_confidence": result.get("decision_confidence"),
            "human_review_required": result.get("human_review_required"),
            "plan_item_count": len(result.get("procurement_plan", []) or []),
        },
    )

    return {
        "decision_aggregation": result,
        "previous_recommendation": result,
        "final_decision": (
            "pending_human_review"
            if result.get("human_review_required")
            else "recommended"
        ),
        "current_agent": "decision_aggregator",
        "reasoning_trace": [
            (
                "Decision aggregator recommended strategy "
                f"'{result.get('recommended_strategy')}'."
            )
        ],
    }


def build_supervisor_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("demand_analyst", demand_analyst_node)
    workflow.add_node("supplier_intelligence", supplier_intelligence_node)
    workflow.add_node("risk_complexity_planner", risk_complexity_planner_node)
    workflow.add_node(
        "strategy_reasoning_executor",
        strategy_reasoning_executor_node,
    )
    workflow.add_node("decision_aggregator", decision_aggregator_node)

    workflow.set_entry_point("demand_analyst")
    workflow.add_edge("demand_analyst", "supplier_intelligence")
    workflow.add_edge("supplier_intelligence", "risk_complexity_planner")
    workflow.add_edge(
        "risk_complexity_planner",
        "strategy_reasoning_executor",
    )
    workflow.add_edge("strategy_reasoning_executor", "decision_aggregator")
    workflow.add_edge("decision_aggregator", END)

    return workflow.compile()


def _validate_workflow_inputs(
    product_id: str,
    demand_forecast: float,
    required_date: str,
) -> None:
    if not product_id or not product_id.strip():
        raise WorkflowExecutionError(
            "Product ID is required.",
            component="supervisor",
        )

    try:
        quantity = float(demand_forecast)
    except (TypeError, ValueError) as exc:
        raise WorkflowExecutionError(
            "Demand forecast must be a valid number.",
            component="supervisor",
        ) from exc

    if quantity <= 0:
        raise WorkflowExecutionError(
            "Demand forecast must be greater than zero.",
            component="supervisor",
        )

    if not required_date:
        raise WorkflowExecutionError(
            "Required date is required.",
            component="supervisor",
        )

    try:
        date.fromisoformat(str(required_date))
    except ValueError as exc:
        raise WorkflowExecutionError(
            "Required date must use ISO format YYYY-MM-DD.",
            component="supervisor",
        ) from exc


@traceable_if_enabled(
    name="Procurement Workflow",
    run_type="chain",
    tags=["forgeforce", "procurement", "supervisor"],
)
def _run_procurement_workflow_traced(
    product_id: str,
    demand_forecast: float,
    required_date: str,
    *,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    langsmith_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the complete procurement analysis workflow.

    session_id and run_id are optional correlation fields. Existing callers that
    provide only product_id, demand_forecast, and required_date remain valid.
    """
    _validate_workflow_inputs(
        product_id=product_id,
        demand_forecast=demand_forecast,
        required_date=required_date,
    )

    context_token = bind_log_context(
        session_id=session_id,
        run_id=run_id,
        product_id=product_id,
        demand_forecast=demand_forecast,
        required_date=required_date,
        supervisor_version=SUPERVISOR_VERSION,
    )
    started_at = time.perf_counter()
    completion_status = "failed"
    completion_payload: Dict[str, Any] = {
        "product_id": product_id,
        "demand_forecast": demand_forecast,
        "required_date": required_date,
    }

    logger.info(
        "procurement_workflow_started",
        component="supervisor",
        status="running",
        payload={
            "product_id": product_id,
            "demand_forecast": demand_forecast,
            "required_date": required_date,
        },
    )

    initial_state: AgentState = {
        "product_id": product_id,
        "product_name": None,
        "current_date": required_date,
        "demand_forecast": demand_forecast,
        "current_stock": None,
        "safety_stock": None,
        "net_requirement": None,
        "inventory_analysis": None,
        "demand_analysis": None,
        "supplier_options": None,
        "recommended_supplier": None,
        "supplier_reasoning": None,
        "alternative_suppliers": None,
        "supplier_intelligence_output": None,
        "risk_complexity_plan": None,
        "contracted_reasoning": None,
        "spot_reasoning": None,
        "decision_aggregation": None,
        "human_approved": None,
        "human_feedback": None,
        "final_decision": "pending",
        "pr_created": False,
        "pr_number": None,
        "po_created": False,
        "po_number": None,
        "execution_notes": None,
        "messages": [],
        "reasoning_trace": [],
        "last_user_question": None,
        "previous_recommendation": None,
        "next_step": None,
        "current_agent": None,
        "error_message": None,
    }

    try:
        app = build_supervisor_graph()
        result = app.invoke(initial_state)

        recommended_strategy = (
            result.get("decision_aggregation") or {}
        ).get("recommended_strategy")
        selected_route = (
            result.get("risk_complexity_plan") or {}
        ).get("selected_route")

        completion_status = "success"
        completion_payload.update({
            "recommended_strategy": recommended_strategy,
            "selected_route": selected_route,
        })

        logger.info(
            "procurement_workflow_succeeded",
            component="supervisor",
            status="success",
            payload={
                "recommended_strategy": recommended_strategy,
                "selected_route": selected_route,
            },
        )
        return result

    except WorkflowExecutionError:
        raise

    except Exception as exc:
        logger.exception(
            "procurement_workflow_failed",
            error=exc,
            component="supervisor",
            status="failed",
            payload={"product_id": product_id},
        )
        raise WorkflowExecutionError(
            f"Procurement workflow failed for product {product_id}.",
            component="supervisor",
            run_id=run_id,
        ) from exc

    finally:
        logger.info(
            "procurement_workflow_completed",
            component="supervisor",
            status=completion_status,
            duration_ms=(time.perf_counter() - started_at) * 1000,
            payload=completion_payload,
        )
        reset_log_context(context_token)


def run_procurement_workflow(
    product_id: str,
    demand_forecast: float,
    required_date: str,
    *,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    langsmith_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the procurement workflow under one searchable parent trace."""
    trace_extra = langsmith_extra or build_langsmith_extra(
        metadata=build_trace_metadata(
            session_id=session_id,
            run_id=run_id,
            product_id=product_id,
            demand_forecast=demand_forecast,
            required_date=required_date,
            component="supervisor",
            supervisor_version=SUPERVISOR_VERSION,
        ),
        tags=["forgeforce", "procurement", "workflow"],
        run_name="Procurement Workflow",
    )
    return _run_procurement_workflow_traced(
        product_id=product_id,
        demand_forecast=demand_forecast,
        required_date=required_date,
        session_id=session_id,
        run_id=run_id,
        langsmith_extra=trace_extra,
    )
