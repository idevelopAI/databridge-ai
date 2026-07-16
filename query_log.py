from contextvars import ContextVar
from typing import Any

SQLExecution = dict[str, Any]

CURRENT_SQL_EXECUTIONS: ContextVar[list[SQLExecution] | None] = ContextVar(
    "CURRENT_SQL_EXECUTIONS",
    default=None,
)


def record_sql_execution(execution: SQLExecution) -> None:
    executions = CURRENT_SQL_EXECUTIONS.get()
    if executions is not None:
        executions.append(execution)
