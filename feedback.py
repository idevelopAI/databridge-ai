import json
import sqlite3
from collections.abc import Iterator
from typing import Literal

from config import get_feedback_db_path

FeedbackRating = Literal["correct", "incorrect"]


def _connect() -> sqlite3.Connection:
    path = get_feedback_db_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS query_feedback (
            question TEXT NOT NULL,
            generated_sql TEXT NOT NULL,
            feedback TEXT NOT NULL CHECK (feedback IN ('correct', 'incorrect'))
        )
        """
    )
    connection.commit()
    path.chmod(0o600)
    return connection


def store_feedback(
    question: str,
    generated_sql: str,
    rating: FeedbackRating,
) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO query_feedback (question, generated_sql, feedback) "
            "VALUES (?, ?, ?)",
            (question, generated_sql, rating),
        )


def iter_feedback_jsonl() -> Iterator[str]:
    with _connect() as connection:
        cursor = connection.execute(
            "SELECT question, generated_sql, feedback "
            "FROM query_feedback ORDER BY rowid"
        )
        for question, generated_sql, rating in cursor:
            yield (
                json.dumps(
                    {
                        "question": question,
                        "generated_sql": generated_sql,
                        "feedback": rating,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
