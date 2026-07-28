import json

import pytest

from privacy_policy import (
    clear_privacy_policy_cache,
    filter_schema_by_policy,
    get_privacy_policy,
    mask_result_rows,
    restricted_question_reason,
    validate_sql_privacy,
)


@pytest.fixture(autouse=True)
def clear_policy_cache():
    clear_privacy_policy_cache()
    yield
    clear_privacy_policy_cache()


def test_default_policy_allows_configured_tables():
    decision = validate_sql_privacy("SELECT name FROM employees ORDER BY name LIMIT 5")

    assert decision.is_allowed is True


def test_default_policy_rejects_unlisted_table():
    decision = validate_sql_privacy("SELECT value FROM application_secrets")

    assert decision.is_allowed is False
    assert decision.reason_code == "restricted_table"
    assert "application_secrets" not in decision.message


def test_default_policy_rejects_restricted_question_without_model_call():
    assert (
        restricted_question_reason("Show every employee social security number")
        == "restricted_field"
    )


def test_direct_salary_is_masked_but_large_enough_aggregate_is_not():
    direct_rows = mask_result_rows(
        "SELECT name, salary FROM employees",
        ["name", "salary"],
        [["Alice", 75000]],
    )
    aggregate_rows = mask_result_rows(
        "SELECT AVG(salary) AS average_salary FROM employees "
        "HAVING COUNT(salary) >= 2",
        ["average_salary"],
        [[87166.67]],
    )

    assert direct_rows == [["Alice", "***"]]
    assert aggregate_rows == [[87166.67]]


@pytest.mark.parametrize(
    "query",
    [
        "SELECT array_agg(salary) FROM employees",
        "SELECT json_agg(salary) FROM employees",
        "SELECT jsonb_agg(salary) FROM employees",
        "SELECT row_to_json(employees) FROM employees",
        "SELECT to_jsonb(e) FROM employees AS e",
        "SELECT e FROM employees AS e",
    ],
)
def test_whole_row_and_collection_disclosures_are_rejected(query):
    decision = validate_sql_privacy(query)

    assert decision.is_allowed is False
    assert decision.reason_code == "restricted_column"


def test_masked_aggregate_requires_minimum_non_null_cohort():
    missing_cohort = validate_sql_privacy(
        "SELECT AVG(salary) AS average_salary FROM employees"
    )
    wrong_count = validate_sql_privacy(
        "SELECT AVG(salary) AS average_salary FROM employees HAVING COUNT(*) >= 2"
    )
    valid_cohort = validate_sql_privacy(
        "SELECT AVG(salary) AS average_salary FROM employees "
        "HAVING COUNT(salary) >= 2"
    )

    assert missing_cohort.reason_code == "aggregate_cohort"
    assert wrong_count.reason_code == "aggregate_cohort"
    assert valid_cohort.is_allowed is True


def test_masked_column_alias_does_not_bypass_masking():
    rows = mask_result_rows(
        "SELECT salary AS harmless_value FROM employees",
        ["harmless_value"],
        [[75000]],
    )

    assert rows == [["***"]]


def test_non_public_schema_with_allowed_table_name_is_rejected():
    decision = validate_sql_privacy("SELECT name FROM private.employees")

    assert decision.is_allowed is False
    assert decision.reason_code == "restricted_table"


def test_identifier_and_email_outputs_are_automatically_masked():
    rows = mask_result_rows(
        "SELECT employee_id, email FROM employees",
        ["employee_id", "email"],
        [[42, "person@example.com"]],
    )

    assert rows == [["***", "***"]]


def test_german_phone_column_is_automatically_masked():
    rows = mask_result_rows(
        "SELECT telefonnummer FROM employees",
        ["telefonnummer"],
        [["private-phone-value"]],
    )

    assert rows == [["***"]]


def test_custom_column_denylist_is_enforced(monkeypatch, tmp_path):
    policy_path = tmp_path / "privacy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "default_schema": "public",
                "tables": {"allow": [], "deny": []},
                "columns": {
                    "allow": [],
                    "deny": ["public.employees.salary"],
                    "mask": {},
                    "restricted_terms": {
                        "public.employees.salary": ["salary", "Gehalt"]
                    },
                },
                "masking": {
                    "enabled": True,
                    "auto_detect": True,
                    "allow_aggregates": True,
                    "minimum_aggregate_group_size": 2,
                    "replacement": "***",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRIVACY_POLICY_PATH", str(policy_path))

    decision = validate_sql_privacy("SELECT salary FROM employees")

    assert decision.is_allowed is False
    assert decision.reason_code == "restricted_column"
    assert restricted_question_reason("What is the salary?") == "restricted_field"


def test_schema_hides_denied_columns(monkeypatch, tmp_path):
    policy_path = tmp_path / "privacy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "default_schema": "public",
                "tables": {"allow": ["public.employees"], "deny": []},
                "columns": {
                    "allow": [],
                    "deny": ["public.employees.private_notes"],
                    "mask": {},
                    "restricted_terms": {
                        "public.employees.private_notes": ["private notes"]
                    },
                },
                "masking": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRIVACY_POLICY_PATH", str(policy_path))
    schema = [
        {
            "name": "employees",
            "columns": [
                {"name": "name"},
                {"name": "private_notes"},
            ],
            "foreign_keys": [],
        },
        {"name": "projects", "columns": [], "foreign_keys": []},
    ]

    filtered = filter_schema_by_policy(schema)

    assert [table["name"] for table in filtered] == ["employees"]
    assert [column["name"] for column in filtered[0]["columns"]] == ["name"]


def test_invalid_policy_fails_closed(monkeypatch, tmp_path):
    policy_path = tmp_path / "privacy.json"
    policy_path.write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.setenv("PRIVACY_POLICY_PATH", str(policy_path))

    with pytest.raises(RuntimeError, match="could not be loaded"):
        get_privacy_policy()
