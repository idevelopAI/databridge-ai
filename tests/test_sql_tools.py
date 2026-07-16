from decimal import Decimal

from sqlalchemy import create_engine, text

from query_log import CURRENT_SQL_EXECUTIONS
from sql_tools import (
    _json_value,
    describe_tables,
    execute_read_only_query,
)


def test_read_only_query_records_structured_execution():
    engine = create_engine("sqlite:///:memory:")
    executions = []
    token = CURRENT_SQL_EXECUTIONS.set(executions)

    try:
        output = execute_read_only_query(
            "SELECT 1 AS value",
            engine=engine,
            max_rows=10,
        )
    finally:
        CURRENT_SQL_EXECUTIONS.reset(token)

    assert output["columns"] == ["value"]
    assert output["rows"] == [[1]]
    assert output["row_count"] == 1
    assert output["truncated"] is False
    assert executions == [output]


def test_read_only_query_caps_rows():
    engine = create_engine("sqlite:///:memory:")
    query = "SELECT 1 AS value UNION ALL SELECT 2 UNION ALL SELECT 3"

    output = execute_read_only_query(query, engine=engine, max_rows=2)

    assert output["rows"] == [[1], [2]]
    assert output["truncated"] is True


def test_unsafe_query_is_not_executed_or_recorded():
    engine = create_engine("sqlite:///:memory:")
    executions = []
    token = CURRENT_SQL_EXECUTIONS.set(executions)

    try:
        output = execute_read_only_query(
            "DROP TABLE employees",
            engine=engine,
            max_rows=10,
        )
    finally:
        CURRENT_SQL_EXECUTIONS.reset(token)

    assert "SQL safety error" in output["error"]
    assert executions == []


def test_describe_tables_rejects_unknown_names():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE employees (id INTEGER PRIMARY KEY)"))

    output = describe_tables("employees, missing", engine=engine)

    assert output == {"error": "Unknown tables: missing"}


def test_decimal_values_are_json_serializable():
    assert _json_value(Decimal("120000.25")) == 120000.25
