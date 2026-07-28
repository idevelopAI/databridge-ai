import json
from types import SimpleNamespace

import pytest

import database_setup
from configuration_validation import validate_configuration_references
from database_setup import (
    DatabaseSetupError,
    _run_check,
    _run_configure,
    _run_validate,
    generate_privacy_policy,
    generate_semantic_layer,
    select_allowed_tables,
    write_generated_configuration,
)
from database_setup import (
    main as setup_main,
)


def sample_metadata():
    return [
        {
            "schema": "public",
            "name": "employees",
            "columns": [
                {
                    "name": "id",
                    "type": "INTEGER",
                    "nullable": False,
                    "flags": ["PK"],
                },
                {
                    "name": "email",
                    "type": "VARCHAR(255)",
                    "nullable": False,
                    "flags": [],
                },
                {
                    "name": "salary",
                    "type": "NUMERIC",
                    "nullable": True,
                    "flags": [],
                },
                {
                    "name": "password_hash",
                    "type": "TEXT",
                    "nullable": True,
                    "flags": [],
                },
            ],
            "foreign_keys": [],
        },
        {
            "schema": "reporting",
            "name": "monthly_totals",
            "columns": [
                {
                    "name": "month",
                    "type": "DATE",
                    "nullable": False,
                    "flags": [],
                }
            ],
            "foreign_keys": [],
        },
    ]


def test_explicit_schema_and_table_selection():
    selected = select_allowed_tables(
        sample_metadata(),
        schemas=["public"],
        tables=["employees"],
    )

    assert [f"{table['schema']}.{table['name']}" for table in selected] == [
        "public.employees"
    ]


def test_all_tables_requires_explicit_schema():
    with pytest.raises(DatabaseSetupError, match="explicit --schema"):
        select_allowed_tables(sample_metadata(), all_tables=True)


def test_generation_detects_masks_and_denied_columns():
    selected = [sample_metadata()[0]]

    policy = generate_privacy_policy(selected, default_schema="public")
    glossary = generate_semantic_layer(selected, default_schema="public")

    assert policy.tables.allow == ["public.employees"]
    assert policy.columns.deny == ["public.employees.password_hash"]
    assert policy.columns.mask == {
        "public.employees.email": "email",
        "public.employees.id": "identifier",
        "public.employees.salary": "salary",
    }
    assert glossary.metrics == {}
    assert glossary.terms == {}
    assert validate_configuration_references(
        policy,
        glossary,
        sample_metadata(),
    ).is_valid


def test_generated_files_are_private_and_not_overwritten(tmp_path):
    selected = [sample_metadata()[0]]
    policy = generate_privacy_policy(selected, default_schema="public")
    glossary = generate_semantic_layer(selected, default_schema="public")
    glossary_path = tmp_path / "semantic.json"
    privacy_path = tmp_path / "privacy.json"

    write_generated_configuration(
        glossary_path=glossary_path,
        privacy_path=privacy_path,
        semantic_layer=glossary,
        privacy_policy=policy,
        force=False,
    )

    assert json.loads(glossary_path.read_text())["version"] == 1
    assert json.loads(privacy_path.read_text())["version"] == 1
    assert glossary_path.stat().st_mode & 0o777 == 0o600
    assert privacy_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(DatabaseSetupError, match="Refusing to overwrite"):
        write_generated_configuration(
            glossary_path=glossary_path,
            privacy_path=privacy_path,
            semantic_layer=glossary,
            privacy_policy=policy,
            force=False,
        )


def test_configure_command_generates_selected_files(monkeypatch, tmp_path):
    connection = SimpleNamespace(
        database="analytics",
        role="report_reader",
        server_version="15.8",
    )
    safe_role = SimpleNamespace(is_safe=True, issues=())
    monkeypatch.setattr(database_setup, "test_connection", lambda engine: connection)
    monkeypatch.setattr(
        database_setup,
        "get_schema_metadata",
        lambda engine: sample_metadata(),
    )
    monkeypatch.setattr(
        database_setup,
        "verify_read_only_role",
        lambda engine, **kwargs: safe_role,
    )
    glossary_path = tmp_path / "glossary.json"
    privacy_path = tmp_path / "privacy.json"
    args = SimpleNamespace(
        schema=["public"],
        table=["public.employees"],
        all_tables=False,
        default_schema=None,
        glossary_output=glossary_path,
        privacy_output=privacy_path,
        force=False,
    )

    result = _run_configure(object(), args)

    assert result == 0
    assert glossary_path.exists()
    assert privacy_path.exists()


def test_check_command_rejects_unsafe_role(monkeypatch, capsys):
    connection = SimpleNamespace(
        database="analytics",
        role="admin",
        server_version="15.8",
    )
    unsafe_role = SimpleNamespace(
        is_safe=False,
        issues=("role is a superuser",),
    )
    monkeypatch.setattr(database_setup, "test_connection", lambda engine: connection)
    monkeypatch.setattr(
        database_setup,
        "get_schema_metadata",
        lambda engine: sample_metadata(),
    )
    monkeypatch.setattr(
        database_setup,
        "verify_read_only_role",
        lambda engine, **kwargs: unsafe_role,
    )

    assert _run_check(object()) == 1
    assert "role is a superuser" in capsys.readouterr().out


def test_validate_command_reports_configuration_issues(monkeypatch, capsys):
    report = SimpleNamespace(
        is_valid=False,
        issues=("configured column does not exist: public.employees.removed",),
    )
    monkeypatch.setattr(
        database_setup,
        "validate_database_configuration",
        lambda engine: report,
    )

    assert _run_validate(object()) == 1
    assert "configured column does not exist" in capsys.readouterr().out


def test_main_reports_configuration_errors_without_traceback(monkeypatch, capsys):
    def unavailable_engine():
        raise RuntimeError("Database is not configured.")

    unavailable_engine.cache_clear = lambda: None
    monkeypatch.setattr(database_setup, "get_engine", unavailable_engine)

    assert setup_main(["check"]) == 1
    assert "Database is not configured." in capsys.readouterr().err
