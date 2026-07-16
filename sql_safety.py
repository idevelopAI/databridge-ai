from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

PROHIBITED_FUNCTIONS = {
    "dblink",
    "lo_export",
    "lo_import",
    "nextval",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "pg_sleep",
    "set_config",
    "setval",
}


@dataclass(frozen=True)
class SQLSafetyResult:
    is_safe: bool
    reason: str = ""


def validate_read_only_sql(sql: str) -> SQLSafetyResult:
    if not sql or not sql.strip():
        return SQLSafetyResult(False, "SQL query is empty.")

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError:
        return SQLSafetyResult(False, "SQL query could not be parsed.")

    if len(statements) != 1:
        return SQLSafetyResult(False, "Only one SQL statement is allowed.")

    statement = statements[0]
    if statement is None:
        return SQLSafetyResult(False, "SQL query is empty.")

    if not isinstance(statement, exp.Query):
        return SQLSafetyResult(False, "Only SELECT queries are allowed.")

    forbidden_nodes = (exp.DDL, exp.DML, exp.Command, exp.Into, exp.Lock)
    if any(isinstance(node, forbidden_nodes) for node in statement.walk()):
        return SQLSafetyResult(
            False, "The query contains a write or locking operation."
        )

    for function in statement.find_all(exp.Func):
        if function.name.lower() in PROHIBITED_FUNCTIONS:
            return SQLSafetyResult(
                False,
                f"The function {function.name} is not allowed in read-only queries.",
            )

    return SQLSafetyResult(True)
