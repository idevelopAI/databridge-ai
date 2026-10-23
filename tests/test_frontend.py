from unittest.mock import Mock

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

SCHEMA = [
    {
        "name": "projects",
        "schema": "public",
        "columns": [
            {"name": "name", "type": "TEXT", "flags": [], "nullable": False},
            {"name": "budget", "type": "NUMERIC", "flags": [], "nullable": True},
        ],
    }
]
ANSWER = {
    "answer": "Two projects matched.",
    "status": "answered",
    "executions": [
        {
            "columns": ["name", "budget"],
            "rows": [["Migration", 50000], ["Website", 25000]],
            "row_count": 2,
            "duration_ms": 2,
            "sql": "SELECT name, budget FROM projects ORDER BY budget DESC",
        }
    ],
}


def response(payload, status=200):
    result = Mock(status_code=status, content=b"")
    result.json.return_value = payload
    return result


@pytest.fixture
def frontend(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "frontend-test-token")
    monkeypatch.setenv("APP_MODE", "recorded")
    get = Mock(return_value=response(SCHEMA))
    post = Mock(return_value=response(ANSWER))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    st.cache_data.clear()
    app = AppTest.from_file("app.py", default_timeout=10).run()
    assert not app.exception
    yield app, get, post
    st.cache_data.clear()


def test_query_results_and_export_keep_composer_available(frontend):
    app, _, post = frontend
    app.button(key="example-0").click().run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert len(app.tabs) == 3
    assert len(app.chat_input) == 1
    assert app.code[0].value == ANSWER["executions"][0]["sql"]
    assert post.call_args.kwargs["json"]["chat_history"] == ""


def test_clarification_can_be_answered_with_context(frontend):
    app, _, post = frontend
    post.return_value = response(
        {"answer": "Annual or monthly salary?", "status": "clarification_required"}
    )
    app.chat_input[0].set_value("Who earns the most?").run()
    assert not app.exception
    assert len(app.chat_input) == 1
    assert app.chat_input[0].placeholder == "Deine Präzisierung..."
    post.return_value = response(ANSWER)
    app.chat_input[0].set_value("Annual gross salary").run()
    assert not app.exception
    history = post.call_args.kwargs["json"]["chat_history"]
    assert "Who earns the most?" in history
    assert "Annual or monthly salary?" in history
    assert len(app.dataframe) == 1


def test_rejected_question_is_visible_but_excluded_from_context(frontend):
    app, _, post = frontend
    post.return_value = response(
        {"detail": "Database modifications are not allowed"}, 403
    )
    app.chat_input[0].set_value("Delete every employee").run()
    assert not app.exception
    assert len(app.warning) == 1
    assert len(app.chat_input) == 1
    post.return_value = response(ANSWER)
    app.chat_input[0].set_value("Show project budgets").run()
    assert post.call_args.kwargs["json"]["chat_history"] == ""


def test_new_chat_and_restore_do_not_reexecute_queries(frontend):
    app, _, post = frontend
    app.chat_input[0].set_value("Show project budgets").run()
    original = app.session_state["active_conversation"]
    app.button(key="new-chat").click().run()
    assert app.session_state["active_conversation"] != original
    assert len(app.chat_message) == 0
    app.button(key=f"conversation-{original}").click().run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert post.call_count == 1


def test_schema_search_does_not_lose_the_conversation(frontend):
    app, _, _ = frontend
    app.chat_input[0].set_value("Show project budgets").run()
    app.button(key="nav-schema").click().run()
    app.text_input(key="schema-search").set_value("missing").run()
    assert len(app.info) == 1
    app.text_input(key="schema-search").set_value("projects").run()
    assert len(app.dataframe) == 1
    app.button(key="nav-chat").click().run()
    assert not app.exception
    assert len(app.chat_message) == 2


def test_feedback_records_only_reviewed_question_and_sql(frontend):
    app, _, post = frontend
    app.chat_input[0].set_value("Show project budgets").run()
    active = app.session_state["active_conversation"]
    app.button(key=f"feedback-correct-{active}-1").click().run()
    assert not app.exception
    assert post.call_args.kwargs["json"] == {
        "question": "Show project budgets",
        "generated_sql": ANSWER["executions"][0]["sql"],
        "feedback": "correct",
    }


def test_backend_failure_keeps_an_actionable_chat(frontend):
    app, _, post = frontend
    post.side_effect = requests.ConnectionError("private connection details")
    app.chat_input[0].set_value("Show project budgets").run()
    assert not app.exception
    assert len(app.warning) == 1
    assert "private connection details" not in app.warning[0].value
    assert len(app.chat_input) == 1
