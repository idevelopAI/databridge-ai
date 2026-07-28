from decimal import Decimal
from unittest.mock import Mock

from sqlalchemy import create_engine, text

from query_log import CURRENT_SQL_EXECUTIONS
from sql_tools import (
    _bound_result_rows,
    _configure_postgresql_transaction,
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


def test_result_cells_and_total_bytes_are_bounded():
    rows, truncated = _bound_result_rows(
        ["value"],
        [["abcdefghijk"], ["second row"]],
        max_cell_bytes=8,
        max_result_bytes=21,
    )

    assert rows == [["abcde..."]]
    assert truncated is True


def test_postgresql_transaction_is_read_only_and_has_local_timeout(monkeypatch):
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "750")
    connection = Mock()

    _configure_postgresql_transaction(connection)

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements == [
        "SET TRANSACTION READ ONLY",
        "SELECT set_config('statement_timeout', :timeout, true)",
    ]
    assert connection.execute.call_args_list[1].args[1] == {"timeout": "750ms"}


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
        "SELECT AVG(salary) AS average_salary FROM employees HAVING COUNT(salary) >= 2",
        engine=engine,
        max_rows=10,
    )

    assert output["rows"] == [[80000.0]]
