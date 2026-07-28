from dataclasses import dataclass

import sqlglot
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp
from sqlglot.errors import ParseError

from database import get_engine, get_schema_metadata
from database_assurance import (
    DatabaseAssuranceError,
    test_connection,
    verify_read_only_role,
)
from privacy_policy import PrivacyPolicy, get_privacy_policy
from semantic_layer import SemanticLayer, get_semantic_layer


@dataclass(frozen=True)
class ConfigurationValidationReport:
    issues: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _identifier(value: str) -> str:
    return value.strip().casefold()


def _actual_columns(schema_metadata: list[dict]) -> dict[str, set[str]]:
    return {
        f"{_identifier(table['schema'])}.{_identifier(table['name'])}": {
            _identifier(column["name"]) for column in table.get("columns", [])
        }
        for table in schema_metadata
    }


def _resolve_table(
    reference: str,
    *,
    default_schema: str,
    actual_tables: set[str],
) -> str:
    normalized = _identifier(reference)
    if normalized.count(".") == 1:
        return normalized
    default_reference = f"{_identifier(default_schema)}.{normalized}"
    if default_reference in actual_tables:
        return default_reference
    matches = {table for table in actual_tables if table.endswith(f".{normalized}")}
    return next(iter(matches)) if len(matches) == 1 else default_reference


def _validate_column_reference(
    reference: str,
    *,
    actual: dict[str, set[str]],
    issues: list[str],
) -> None:
    table_reference, _, column_name = _identifier(reference).rpartition(".")
    if table_reference not in actual:
        issues.append(f"configured table does not exist: {table_reference}")
    elif column_name not in actual[table_reference]:
        issues.append(f"configured column does not exist: {reference}")


def _validate_expression_columns(
    *,
    label: str,
    expression: str,
    table_references: set[str],
    actual: dict[str, set[str]],
    issues: list[str],
) -> None:
    try:
        parsed = sqlglot.parse_one(expression, read="postgres")
    except ParseError:
        issues.append(f"{label} contains invalid SQL metadata")
        return
    if parsed is None:
        issues.append(f"{label} contains invalid SQL metadata")
        return

    for column in parsed.find_all(exp.Column):
        column_name = _identifier(column.name)
        qualifier = _identifier(column.table)
        candidates = (
            {table for table in table_references if table.endswith(f".{qualifier}")}
            if qualifier
            else table_references
        )
        matching = {
            table for table in candidates if column_name in actual.get(table, set())
        }
        if len(matching) != 1:
            issues.append(
                f"{label} references a missing or ambiguous column: {column.sql()}"
            )


def validate_configuration_references(
    privacy_policy: PrivacyPolicy,
    semantic_layer: SemanticLayer,
    schema_metadata: list[dict],
) -> ConfigurationValidationReport:
    actual = _actual_columns(schema_metadata)
    actual_tables = set(actual)
    issues: list[str] = []

    configured_tables = {
        _identifier(reference)
        for reference in [
            *privacy_policy.tables.allow,
            *privacy_policy.tables.deny,
        ]
    }
    for table_reference in configured_tables:
        if table_reference not in actual_tables:
            issues.append(f"configured table does not exist: {table_reference}")

    configured_columns = {
        _identifier(reference)
        for reference in [
            *privacy_policy.columns.allow,
            *privacy_policy.columns.deny,
            *privacy_policy.columns.mask,
            *privacy_policy.columns.restricted_terms,
        ]
    }
    for column_reference in configured_columns:
        _validate_column_reference(
            column_reference,
            actual=actual,
            issues=issues,
        )

    allowed_tables = {
        _identifier(reference) for reference in privacy_policy.tables.allow
    }
    for table_name, table in semantic_layer.tables.items():
        table_reference = _resolve_table(
            table_name,
            default_schema=privacy_policy.default_schema,
            actual_tables=actual_tables,
        )
        if table_reference not in actual:
            issues.append(f"glossary table does not exist: {table_name}")
            continue
        if allowed_tables and table_reference not in allowed_tables:
            issues.append(f"glossary table is not allowed: {table_name}")
        for column_name in table.columns:
            if _identifier(column_name) not in actual[table_reference]:
                issues.append(
                    f"glossary column does not exist: {table_name}.{column_name}"
                )

    for category, entries in (
        ("metric", semantic_layer.metrics),
        ("term", semantic_layer.terms),
    ):
        for name, entry in entries.items():
            table_references = {
                _resolve_table(
                    table_name,
                    default_schema=privacy_policy.default_schema,
                    actual_tables=actual_tables,
                )
                for table_name in entry.tables
            }
            for table_reference in table_references:
                if table_reference not in actual:
                    issues.append(
                        f"{category} {name} references a missing table: "
                        f"{table_reference}"
                    )
                elif allowed_tables and table_reference not in allowed_tables:
                    issues.append(
                        f"{category} {name} references a restricted table: "
                        f"{table_reference}"
                    )
            sql_metadata = entry.expression if category == "metric" else entry.condition
            _validate_expression_columns(
                label=f"{category} {name}",
                expression=sql_metadata,
                table_references=table_references,
                actual=actual,
                issues=issues,
            )

    return ConfigurationValidationReport(issues=tuple(sorted(set(issues))))


def validate_database_configuration(
    engine: Engine | None = None,
) -> ConfigurationValidationReport:
    active_engine = engine or get_engine()
    try:
        test_connection(active_engine)
        privacy_policy = get_privacy_policy()
        semantic_layer = get_semantic_layer()
        schema_metadata = get_schema_metadata(active_engine)
        references = validate_configuration_references(
            privacy_policy,
            semantic_layer,
            schema_metadata,
        )
        role = verify_read_only_role(
            active_engine,
            schema_metadata=schema_metadata,
            required_tables=set(privacy_policy.tables.allow),
        )
    except (DatabaseAssuranceError, RuntimeError, SQLAlchemyError):
        return ConfigurationValidationReport(
            issues=("database configuration validation failed",)
        )

    return ConfigurationValidationReport(
        issues=tuple(
            sorted(
                {
                    *references.issues,
                    *(f"database role: {issue}" for issue in role.issues),
                }
            )
        )
    )
