from sql_safety import validate_read_only_sql


def test_allows_select_query():
    result = validate_read_only_sql("SELECT name FROM employees WHERE salary > 100000")

    assert result.is_safe


def test_allows_single_trailing_semicolon():
    assert validate_read_only_sql("SELECT name FROM employees;").is_safe


def test_allows_read_only_cte_and_union():
    query = "WITH ids AS (SELECT id FROM employees) SELECT id FROM ids UNION SELECT 0"

    assert validate_read_only_sql(query).is_safe


def test_rejects_multiple_statements():
    result = validate_read_only_sql("SELECT * FROM employees; DROP TABLE employees;")

    assert not result.is_safe
    assert "Only one SQL statement" in result.reason


def test_rejects_mutating_keyword_in_cte():
    query = "WITH deleted AS (DELETE FROM employees RETURNING *) SELECT * FROM deleted"

    result = validate_read_only_sql(query)

    assert not result.is_safe
    assert "write or locking" in result.reason


def test_rejects_select_into():
    result = validate_read_only_sql("SELECT * INTO employee_copy FROM employees")

    assert not result.is_safe


def test_rejects_row_locks():
    result = validate_read_only_sql("SELECT * FROM employees FOR UPDATE")

    assert not result.is_safe


def test_rejects_prohibited_functions():
    result = validate_read_only_sql("SELECT pg_sleep(1)")

    assert not result.is_safe
    assert "pg_sleep" in result.reason


def test_ignores_mutating_words_inside_string_literals():
    result = validate_read_only_sql("SELECT 'drop table employees' AS warning")

    assert result.is_safe
