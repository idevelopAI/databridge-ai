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
