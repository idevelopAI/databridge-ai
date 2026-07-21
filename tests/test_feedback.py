import json
import sqlite3

from feedback import iter_feedback_jsonl, store_feedback


def test_feedback_database_stores_only_required_fields(monkeypatch, tmp_path):
    database_path = tmp_path / "feedback.db"
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(database_path))

    store_feedback(
        "How many employees are there?",
        "SELECT COUNT(*) FROM employees",
        "correct",
    )

    with sqlite3.connect(database_path) as connection:
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(query_feedback)")
        ]
        stored = connection.execute("SELECT * FROM query_feedback").fetchone()

    assert columns == ["question", "generated_sql", "feedback"]
    assert stored == (
        "How many employees are there?",
        "SELECT COUNT(*) FROM employees",
        "correct",
    )
    assert database_path.stat().st_mode & 0o777 == 0o600


def test_feedback_export_is_jsonl_with_no_extra_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(tmp_path / "feedback.db"))
    store_feedback("Question", "SELECT 1", "incorrect")

    records = [json.loads(line) for line in iter_feedback_jsonl()]

    assert records == [
        {
            "question": "Question",
            "generated_sql": "SELECT 1",
            "feedback": "incorrect",
        }
    ]
