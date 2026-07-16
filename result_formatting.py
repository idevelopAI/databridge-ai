from typing import Any, Literal

INCOMPLETE_ENDINGS = (
    " is",
    " are",
    " equals",
    " ist",
    " sind",
    " beträgt",
    " betragen",
    ":",
)


def format_sql_result_preview(execution: dict[str, Any]) -> str:
    rows = execution.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return ""

    formatted_rows = []
    for row in rows[:5]:
        if isinstance(row, list):
            formatted_rows.append(", ".join(str(value) for value in row))
        else:
            formatted_rows.append(str(row))

    preview = "; ".join(formatted_rows)
    if execution.get("truncated"):
        preview += "; ..."
    return preview


def ensure_answer_includes_result(
    answer: str,
    executions: list[dict[str, Any]],
    *,
    language: Literal["de", "en"] = "de",
) -> str:
    clean_answer = answer.strip()
    if not executions:
        return clean_answer

    preview = format_sql_result_preview(executions[-1])
    if not preview:
        return clean_answer

    normalized_answer = clean_answer.lower().rstrip()
    is_incomplete = not clean_answer or normalized_answer.endswith(INCOMPLETE_ENDINGS)
    if not is_incomplete:
        return clean_answer

    if clean_answer:
        return f"{clean_answer} {preview}."

    prefix = (
        "Das verifizierte Ergebnis ist"
        if language == "de"
        else "The verified result is"
    )
    return f"{prefix} {preview}."
