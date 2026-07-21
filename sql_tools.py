from datetime import date, datetime, time
from decimal import Decimal
from time import perf_counter
from typing import Any
from uuid import UUID

from langchain.tools import tool
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config import get_max_result_rows, is_query_plan_guard_enabled
from database import get_engine, get_schema_metadata
from observability import record_rejection, record_sql_duration
from privacy_policy import (
    filter_schema_by_policy,
    mask_result_rows,
    validate_sql_privacy,
)
from query_log import record_sql_execution
from query_plan import inspect_query_plan
from semantic_layer import get_semantic_layer_data
from sql_safety import validate_read_only_sql


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return "<binary>"
    return str(value)


def execute_read_only_query(
    query: str,
    *,
    engine: Engine | None = None,
    max_rows: int | None = None,
    mask_results: bool = True,
) -> dict[str, Any]:
    safety = validate_read_only_sql(query)
    if not safety.is_safe:
        reason = "sql_parse" if "parsed" in safety.reason else "sql_prohibited"
        record_rejection("sql_safety", reason)
        return {"error": f"SQL safety error: {safety.reason}"}

    privacy = validate_sql_privacy(query)
    if not privacy.is_allowed:
        record_rejection("privacy", privacy.reason_code)
        return {"error": f"Privacy policy rejected the query: {privacy.message}"}

    row_limit = max_rows if max_rows is not None else get_max_result_rows()
    started_at = perf_counter()

    active_engine = engine or get_engine()

    try:
        with active_engine.connect() as connection:
            if (
                active_engine.dialect.name == "postgresql"
                and is_query_plan_guard_enabled()
            ):
                plan_result = inspect_query_plan(connection, query)
                if not plan_result.is_safe:
                    reason = {
                        "the estimated query cost is too high": "plan_cost",
                        "the estimated result is too large": "plan_rows",
                        "the query requires a large full-table scan": "plan_full_scan",
                        "the query creates a large Cartesian join": (
                            "plan_cartesian_join"
                        ),
                    }.get(plan_result.reason, "plan_uninspectable")
                    record_rejection("query_plan", reason)
                    return {"error": f"Query plan rejected: {plan_result.reason}."}

            result = connection.execute(text(query))
            if not result.returns_rows:
                record_rejection("sql_safety", "non_row_result")
                return {"error": "The database query did not return rows."}

            columns = list(result.keys())
            raw_rows = result.fetchmany(row_limit + 1)
    except SQLAlchemyError:
        record_rejection("sql_safety", "database_error")
        return {
            "error": (
                "Database rejected the query. Reinspect the relevant schema and "
                "correct the table, column, or SQL syntax."
            )
        }

    truncated = len(raw_rows) > row_limit
    visible_rows = raw_rows[:row_limit]
    rows = [[_json_value(value) for value in row] for row in visible_rows]
    if mask_results:
        rows = mask_result_rows(query, columns, rows)
    duration_seconds = perf_counter() - started_at
    record_sql_duration(duration_seconds)
    execution = {
        "sql": query.strip(),
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "duration_ms": round(duration_seconds * 1000),
    }
    record_sql_execution(execution)
    return execution


def describe_tables(
    table_names: str,
    *,
    engine: Engine | None = None,
) -> dict[str, Any]:
    requested_names = {
        table_name.strip()
        for table_name in table_names.split(",")
        if table_name.strip()
    }
    if not requested_names:
        return {"error": "At least one table name is required."}

    schema = filter_schema_by_policy(get_schema_metadata(engine))
    known_names = {table["name"] for table in schema}
    unknown_names = sorted(requested_names - known_names)
    if unknown_names:
        return {"error": f"Unknown tables: {', '.join(unknown_names)}"}

    return {"tables": [table for table in schema if table["name"] in requested_names]}


@tool("sql_db_list_tables")
def sql_db_list_tables() -> dict[str, list[str]]:
    """List the PostgreSQL tables available to the read-only database agent."""
    schema = filter_schema_by_policy(get_schema_metadata())
    return {"tables": [table["name"] for table in schema]}


@tool("sql_db_schema")
def sql_db_schema(table_names: str) -> dict[str, Any]:
    """Return columns, keys, and relationships for comma-separated table names."""
    return describe_tables(table_names)


@tool("sql_db_business_glossary")
def sql_db_business_glossary() -> dict[str, Any]:
    """Return trusted business terms, aliases, metrics, and SQL definitions."""
    return get_semantic_layer_data()


@tool("sql_db_query")
def sql_db_query(query: str) -> dict[str, Any]:
    """Execute one parsed, read-only PostgreSQL query and return bounded JSON rows."""
    return execute_read_only_query(query)


def build_sql_tools() -> list:
    return [
        sql_db_list_tables,
        sql_db_business_glossary,
        sql_db_schema,
        sql_db_query,
    ]
