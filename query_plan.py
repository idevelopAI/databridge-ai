import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from config import (
    get_max_cartesian_join_rows,
    get_max_query_plan_cost,
    get_max_query_plan_rows,
    get_max_sequential_scan_rows,
)


@dataclass(frozen=True)
class QueryPlanLimits:
    max_total_cost: float
    max_result_rows: int
    max_sequential_scan_rows: int
    max_cartesian_join_rows: int


@dataclass(frozen=True)
class QueryPlanResult:
    is_safe: bool
    reason: str = ""


def get_query_plan_limits() -> QueryPlanLimits:
    return QueryPlanLimits(
        max_total_cost=get_max_query_plan_cost(),
        max_result_rows=get_max_query_plan_rows(),
        max_sequential_scan_rows=get_max_sequential_scan_rows(),
        max_cartesian_join_rows=get_max_cartesian_join_rows(),
    )


def _plan_root(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError("Unexpected query-plan response.")
    root = payload[0].get("Plan")
    if not isinstance(root, dict):
        raise ValueError("Query plan has no root node.")
    return root


def _walk_plan(node: dict[str, Any]):
    yield node
    for child in node.get("Plans", []):
        if isinstance(child, dict):
            yield from _walk_plan(child)


def _has_join_condition(node: dict[str, Any]) -> bool:
    condition_keys = {
        "Hash Cond",
        "Index Cond",
        "Join Filter",
        "Merge Cond",
        "Recheck Cond",
    }
    return any(node.get(key) for key in condition_keys)


def evaluate_query_plan(
    payload: Any,
    limits: QueryPlanLimits,
) -> QueryPlanResult:
    try:
        root = _plan_root(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return QueryPlanResult(False, "the query plan could not be inspected")

    if float(root.get("Total Cost", 0)) > limits.max_total_cost:
        return QueryPlanResult(False, "the estimated query cost is too high")

    if int(root.get("Plan Rows", 0)) > limits.max_result_rows:
        return QueryPlanResult(False, "the estimated result is too large")

    for node in _walk_plan(root):
        plan_rows = int(node.get("Plan Rows", 0))
        node_type = node.get("Node Type")

        if node_type == "Seq Scan" and plan_rows > limits.max_sequential_scan_rows:
            return QueryPlanResult(False, "the query requires a large full-table scan")

        if (
            node_type == "Nested Loop"
            and plan_rows > limits.max_cartesian_join_rows
            and len(node.get("Plans", [])) >= 2
            and not _has_join_condition(node)
        ):
            return QueryPlanResult(False, "the query creates a large Cartesian join")

    return QueryPlanResult(True)


def inspect_query_plan(connection: Connection, query: str) -> QueryPlanResult:
    try:
        payload = connection.execute(
            text(f"EXPLAIN (FORMAT JSON) {query}")
        ).scalar_one()
    except SQLAlchemyError:
        return QueryPlanResult(False, "the query plan could not be inspected")
    return evaluate_query_plan(payload, get_query_plan_limits())
