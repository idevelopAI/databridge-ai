import math
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from numbers import Real
from typing import Any

from evaluation.models import ExpectedResult


@dataclass(frozen=True)
class ComparisonResult:
    equivalent: bool
    reason: str = ""


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _values_equal(actual: Any, expected: Any) -> bool:
    actual = _normalize(actual)
    expected = _normalize(expected)
    if (
        isinstance(actual, Real)
        and not isinstance(actual, bool)
        and isinstance(expected, Real)
        and not isinstance(expected, bool)
    ):
        return math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=0.01)
    return actual == expected


def _rows_equal(actual: list[Any], expected: list[Any]) -> bool:
    return len(actual) == len(expected) and all(
        _values_equal(actual_value, expected_value)
        for actual_value, expected_value in zip(actual, expected, strict=True)
    )


def _unordered_rows_equal(actual: list[list[Any]], expected: list[list[Any]]) -> bool:
    remaining = list(expected)
    for actual_row in actual:
        match_index = next(
            (
                index
                for index, expected_row in enumerate(remaining)
                if _rows_equal(actual_row, expected_row)
            ),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)
    return not remaining


def compare_execution(
    execution: dict[str, Any],
    expected: ExpectedResult,
    *,
    require_column_names: bool = False,
) -> ComparisonResult:
    columns = execution.get("columns", [])
    rows = execution.get("rows", [])

    if len(columns) != len(expected.columns):
        return ComparisonResult(False, "column count differs")
    if require_column_names and columns != expected.columns:
        return ComparisonResult(False, "column names differ")
    if len(rows) != len(expected.rows):
        return ComparisonResult(False, "row count differs")

    if expected.ordered:
        equivalent = all(
            _rows_equal(actual_row, expected_row)
            for actual_row, expected_row in zip(rows, expected.rows, strict=True)
        )
    else:
        equivalent = _unordered_rows_equal(rows, expected.rows)

    return ComparisonResult(equivalent, "" if equivalent else "row values differ")
