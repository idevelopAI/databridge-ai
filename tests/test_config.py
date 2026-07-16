import pytest

from config import get_database_url, get_max_result_rows


def test_database_url_can_be_built_from_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "db")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "company_data")
    monkeypatch.setenv("DB_USER", "ai_agent_user")
    monkeypatch.setenv("AI_AGENT_DB_PASSWORD", "read only password")

    assert (
        get_database_url()
        == "postgresql+psycopg2://ai_agent_user:read+only+password@db:5433/company_data"
    )


def test_database_url_prefers_explicit_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://example")

    assert get_database_url() == "postgresql+psycopg2://example"


def test_max_result_rows_uses_configured_positive_integer(monkeypatch):
    monkeypatch.setenv("MAX_RESULT_ROWS", "25")

    assert get_max_result_rows() == 25


def test_max_result_rows_rejects_zero(monkeypatch):
    monkeypatch.setenv("MAX_RESULT_ROWS", "0")

    with pytest.raises(RuntimeError, match="greater than zero"):
        get_max_result_rows()
