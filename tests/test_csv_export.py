import csv
import io

from csv_export import rows_to_csv, safe_csv_value


def test_safe_csv_value_neutralizes_spreadsheet_formulas():
    assert safe_csv_value("=2+2") == "'=2+2"
    assert safe_csv_value("+SUM(A1:A2)") == "'+SUM(A1:A2)"
    assert safe_csv_value("@command") == "'@command"
    assert safe_csv_value(-10) == -10
    assert safe_csv_value("ordinary text") == "ordinary text"


def test_rows_to_csv_writes_bom_headers_and_safe_values():
    exported = rows_to_csv(
        ["name", "formula"],
        [["Alice", "=2+2"], ["Bob", None]],
    )

    assert exported.startswith("\ufeff")
    rows = list(csv.reader(io.StringIO(exported.removeprefix("\ufeff"))))
    assert rows == [
        ["name", "formula"],
        ["Alice", "'=2+2"],
        ["Bob", ""],
    ]
