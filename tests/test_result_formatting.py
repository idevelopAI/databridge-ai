from result_formatting import ensure_answer_includes_result, format_sql_result_preview

EXECUTION = {
    "columns": ["name", "salary"],
    "rows": [["Bob Jones", 120000.0]],
    "truncated": False,
}


def test_format_sql_result_preview_flattens_rows():
    assert format_sql_result_preview(EXECUTION) == "Bob Jones, 120000.0"


def test_answer_fallback_completes_an_incomplete_answer():
    answer = ensure_answer_includes_result("Der Mitarbeiter ist", [EXECUTION])

    assert answer == "Der Mitarbeiter ist Bob Jones, 120000.0."


def test_answer_fallback_leaves_complete_answer_unchanged():
    answer = "Bob Jones verdient mit 120000.0 am meisten."

    assert ensure_answer_includes_result(answer, [EXECUTION]) == answer


def test_empty_answer_uses_localized_fallback():
    answer = ensure_answer_includes_result("", [EXECUTION], language="en")

    assert answer == "The verified result is Bob Jones, 120000.0."
