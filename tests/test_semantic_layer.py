import pytest

from semantic_layer import (
    clear_semantic_layer_cache,
    get_semantic_layer,
    semantic_context_for_question,
)


def test_default_semantic_layer_defines_active_projects():
    layer = get_semantic_layer()

    assert layer.version == 1
    assert layer.terms["active_project"].condition == "projects.status = 'active'"
    assert layer.metrics["average_salary"].expression == "AVG(employees.salary)"


def test_context_matches_german_metric_and_tables():
    context = semantic_context_for_question(
        "Wie hoch ist das durchschnittliche Gehalt pro Abteilung?"
    )

    assert "average_salary" in context["metrics"]
    assert "employees" in context["tables"]
    assert "departments" in context["tables"]


def test_context_returns_only_relevant_metadata():
    context = semantic_context_for_question("Hello there")

    assert context == {"tables": {}, "metrics": {}, "terms": {}}


def test_invalid_semantic_layer_is_rejected(monkeypatch, tmp_path):
    invalid_path = tmp_path / "semantic.json"
    invalid_path.write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.setenv("SEMANTIC_LAYER_PATH", str(invalid_path))
    clear_semantic_layer_cache()

    with pytest.raises(RuntimeError, match="could not be loaded"):
        get_semantic_layer()

    clear_semantic_layer_cache()
