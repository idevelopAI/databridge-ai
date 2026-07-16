import csv
import io
from collections.abc import Iterable
from typing import Any

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_csv_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


def rows_to_csv(columns: Iterable[Any], rows: Iterable[Iterable[Any]]) -> str:
    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(safe_csv_value(value) for value in columns)
    for row in rows:
        writer.writerow(safe_csv_value(value) for value in row)
    return output.getvalue()
