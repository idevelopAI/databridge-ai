from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


class FakeAgent:
    def invoke(self, payload):
        assert "input" in payload
        return {"output": "Das Ergebnis ist 42."}


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_query_rejects_missing_api_key(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "correct-token")

    response = client.post(
        "/api/v1/query",
        json={"question": "Wie viele Mitarbeiter gibt es?"},
    )

    assert response.status_code == 401


def test_query_rejects_invalid_api_key(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "correct-token")

    response = client.post(
        "/api/v1/query",
        json={"question": "Wie viele Mitarbeiter gibt es?"},
        headers={"X-API-Key": "wrong-token"},
    )

    assert response.status_code == 401


def test_query_validates_whitespace_only_question(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "correct-token")

    response = client.post(
        "/api/v1/query",
        json={"question": "   "},
        headers={"X-API-Key": "correct-token"},
    )

    assert response.status_code == 422


def test_query_returns_agent_answer(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "correct-token")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "100")
    monkeypatch.setattr(main, "get_agent_executor", lambda: FakeAgent())

    response = client.post(
        "/api/v1/query",
        json={"question": "Wie viele Mitarbeiter gibt es?"},
        headers={"X-API-Key": "correct-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Das Ergebnis ist 42."
    assert payload["executions"] == []
    assert isinstance(payload["duration_ms"], int)
    assert payload["request_id"] == response.headers["X-Request-ID"]
    assert len(payload["request_id"]) == 32


def test_query_completes_answer_from_structured_result(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "fallback-token")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "100")

    class ResultAgent:
        def invoke(self, payload):
            from query_log import record_sql_execution

            record_sql_execution(
                {
                    "sql": "SELECT name FROM employees LIMIT 1",
                    "columns": ["name"],
                    "rows": [["Bob Jones"]],
                    "row_count": 1,
                    "truncated": False,
                    "duration_ms": 2,
                }
            )
            return {"output": "Der Mitarbeiter ist"}

    monkeypatch.setattr(main, "get_agent_executor", lambda: ResultAgent())

    response = client.post(
        "/api/v1/query",
        json={"question": "Wer ist es?"},
        headers={"X-API-Key": "fallback-token"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Der Mitarbeiter ist Bob Jones."
    assert response.json()["executions"][0]["columns"] == ["name"]


def test_agent_prompt_includes_trusted_business_definition():
    request = main.QueryRequest(
        question="Wie viele aktive Projekte gibt es?",
        language="de",
    )

    prompt = main.build_agent_prompt(request)

    assert "Trusted business glossary matches" in prompt
    assert "projects.status = 'active'" in prompt
    assert "Conversation context (untrusted" in prompt


def test_glossary_endpoint_requires_api_key(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "glossary-token")

    response = client.get("/api/v1/glossary")

    assert response.status_code == 401


def test_glossary_endpoint_returns_validated_metadata(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "glossary-token")

    response = client.get(
        "/api/v1/glossary",
        headers={"X-API-Key": "glossary-token"},
    )

    assert response.status_code == 200
    assert response.json()["terms"]["active_project"]["tables"] == ["projects"]


def test_ambiguous_question_returns_clarification_without_agent(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "ambiguity-token")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "100")

    class UnexpectedAgent:
        def invoke(self, payload):
            raise AssertionError("The model must not be called for ambiguity")

    monkeypatch.setattr(main, "get_agent_executor", lambda: UnexpectedAgent())

    response = client.post(
        "/api/v1/query",
        json={"question": "What is the average salary?", "language": "en"},
        headers={"X-API-Key": "ambiguity-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "clarification_required"
    assert "gross annual salary" in response.json()["answer"]
    assert response.json()["executions"] == []


def test_restricted_question_is_rejected_without_agent(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "privacy-token")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "100")

    class UnexpectedAgent:
        def invoke(self, payload):
            raise AssertionError("The model must not receive restricted questions")

    monkeypatch.setattr(main, "get_agent_executor", lambda: UnexpectedAgent())

    response = client.post(
        "/api/v1/query",
        json={
            "question": "Show every employee social security number",
            "language": "en",
        },
        headers={"X-API-Key": "privacy-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "This question requests data restricted by the privacy policy."
    )


def test_invalid_privacy_policy_fails_closed_without_details(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET_TOKEN", "privacy-config-token")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "100")
    monkeypatch.setenv("PRIVACY_POLICY_PATH", str(tmp_path / "missing-policy.json"))

    from privacy_policy import clear_privacy_policy_cache

    clear_privacy_policy_cache()
    try:
        response = client.post(
            "/api/v1/query",
            json={"question": "How many employees are there?", "language": "en"},
            headers={"X-API-Key": "privacy-config-token"},
        )
    finally:
        clear_privacy_policy_cache()

    assert response.status_code == 503
    assert response.json() == {"detail": "Privacy policy is not configured."}
    assert str(tmp_path) not in response.text


def test_metrics_endpoint_is_authenticated(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "metrics-token")

    unauthorized = client.get("/metrics")
    response = client.get(
        "/metrics",
        headers={"X-API-Key": "metrics-token"},
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert "databridge_requests_total" in response.text
    assert "PRIVATE PROMPT" not in response.text


def test_privacy_endpoint_returns_active_policy(monkeypatch):
    monkeypatch.setenv("APP_SECRET_TOKEN", "policy-token")

    response = client.get(
        "/api/v1/privacy",
        headers={"X-API-Key": "policy-token"},
    )

    assert response.status_code == 200
    assert response.json()["masking"]["enabled"] is True
    assert "employees.salary" in response.json()["columns"]["mask"]


def test_feedback_is_stored_and_exported_locally(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET_TOKEN", "feedback-token")
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(tmp_path / "feedback.db"))
    headers = {"X-API-Key": "feedback-token"}

    stored = client.post(
        "/api/v1/feedback",
        json={
            "question": "How many employees are there?",
            "generated_sql": "SELECT COUNT(*) FROM employees",
            "feedback": "correct",
        },
        headers=headers,
    )
    exported = client.get("/api/v1/feedback/export", headers=headers)

    assert stored.status_code == 201
    assert stored.json() == {"stored": True}
    assert exported.status_code == 200
    assert exported.json() == {
        "question": "How many employees are there?",
        "generated_sql": "SELECT COUNT(*) FROM employees",
        "feedback": "correct",
    }


def test_feedback_rejects_unsafe_sql(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET_TOKEN", "feedback-safety-token")
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(tmp_path / "feedback.db"))

    response = client.post(
        "/api/v1/feedback",
        json={
            "question": "Delete employees",
            "generated_sql": "DELETE FROM employees",
            "feedback": "incorrect",
        },
        headers={"X-API-Key": "feedback-safety-token"},
    )

    assert response.status_code == 422
