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


def test_database_errors_do_not_expose_driver_details():
    engine = create_engine("sqlite:///:memory:")

    output = execute_read_only_query(
        "SELECT confidential_column FROM employees",
        engine=engine,
        max_rows=10,
    )

    assert output == {
        "error": (
            "Database rejected the query. Reinspect the relevant schema and "
            "correct the table, column, or SQL syntax."
        )
    }


def test_direct_salary_values_are_masked_before_recording():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE employees (name TEXT, salary INT)"))
        connection.execute(text("INSERT INTO employees VALUES ('Alice', 75000)"))

    output = execute_read_only_query(
        "SELECT name, salary FROM employees",
        engine=engine,
        max_rows=10,
    )

    assert output["rows"] == [["Alice", "***"]]


def test_salary_aggregates_remain_usable():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE employees (salary INT)"))
        connection.execute(text("INSERT INTO employees VALUES (75000), (85000)"))

    output = execute_read_only_query(
        "SELECT AVG(salary) AS average_salary FROM employees",
        engine=engine,
        max_rows=10,
    )

    assert output["rows"] == [[80000.0]]
