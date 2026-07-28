import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from configuration_validation import (
    validate_configuration_references,
    validate_database_configuration,
)
from database import get_engine, get_schema_metadata
from database_assurance import (
    DatabaseAssuranceError,
    test_connection,
    verify_read_only_role,
)
from privacy_policy import PrivacyPolicy, detect_mask_strategy
from semantic_layer import SemanticLayer

SENSITIVE_DENY_TOKENS = {
    "access_token",
    "api_key",
    "card_number",
    "client_secret",
    "credit_card",
    "credential",
    "cvv",
    "iban",
    "national_id",
    "password",
    "password_hash",
    "private_key",
    "private_note",
    "private_notes",
    "secret",
    "social_security",
    "ssn",
    "tax_id",
}


class DatabaseSetupError(RuntimeError):
    pass


def _normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _humanize(value: str) -> str:
    return " ".join(part for part in re.split(r"[_\W]+", value) if part)


def _is_sensitive_deny_column(name: str) -> bool:
    normalized = _normalized_name(name)
    return any(
        normalized == token
        or normalized.startswith(f"{token}_")
        or normalized.endswith(f"_{token}")
        for token in SENSITIVE_DENY_TOKENS
    )


def _table_reference(table: dict) -> str:
    return f"{table['schema']}.{table['name']}"


def _available_table_map(schema_metadata: list[dict]) -> dict[str, dict]:
    return {_table_reference(table).casefold(): table for table in schema_metadata}


def select_allowed_tables(
    schema_metadata: list[dict],
    *,
    schemas: list[str] | None = None,
    tables: list[str] | None = None,
    all_tables: bool = False,
) -> list[dict]:
    available = _available_table_map(schema_metadata)
    requested_schemas = {value.casefold() for value in schemas or []}
    known_schemas = {str(table["schema"]).casefold() for table in schema_metadata}
    unknown_schemas = sorted(requested_schemas - known_schemas)
    if unknown_schemas:
        raise DatabaseSetupError(f"Unknown schemas: {', '.join(unknown_schemas)}")

    candidates = [
        table
        for table in schema_metadata
        if not requested_schemas or str(table["schema"]).casefold() in requested_schemas
    ]
    if all_tables:
        if not requested_schemas:
            raise DatabaseSetupError(
                "--all-tables requires at least one explicit --schema."
            )
        selected = candidates
    elif tables:
        selected = []
        for requested_table in tables:
            normalized = requested_table.casefold()
            if "." in normalized:
                table = available.get(normalized)
                if table is None or table not in candidates:
                    raise DatabaseSetupError(
                        f"Unknown or excluded table: {requested_table}"
                    )
            else:
                matches = [
                    table
                    for table in candidates
                    if str(table["name"]).casefold() == normalized
                ]
                if len(matches) != 1:
                    raise DatabaseSetupError(
                        f"Table name is missing or ambiguous: {requested_table}"
                    )
                table = matches[0]
            if table not in selected:
                selected.append(table)
    else:
        raise DatabaseSetupError("Select at least one table.")

    if not selected:
        raise DatabaseSetupError("No accessible tables matched the selection.")
    return sorted(selected, key=_table_reference)


def _semantic_table_key(
    table: dict,
    *,
    default_schema: str,
    duplicate_names: set[str],
) -> str:
    table_name = str(table["name"])
    if (
        str(table["schema"]).casefold() == default_schema.casefold()
        and table_name.casefold() not in duplicate_names
    ):
        return table_name
    return _table_reference(table)


def generate_semantic_layer(
    selected_tables: list[dict],
    *,
    default_schema: str,
) -> SemanticLayer:
    name_counts = Counter(str(table["name"]).casefold() for table in selected_tables)
    duplicate_names = {name for name, count in name_counts.items() if count > 1}
    tables = {}
    for table in selected_tables:
        reference = _table_reference(table)
        table_name = str(table["name"])
        key = _semantic_table_key(
            table,
            default_schema=default_schema,
            duplicate_names=duplicate_names,
        )
        columns = {}
        for column in table.get("columns", []):
            flags = ", ".join(column.get("flags", []))
            qualifiers = [
                "nullable" if column.get("nullable", True) else "required",
                flags if flags else "",
            ]
            details = ", ".join(value for value in qualifiers if value)
            columns[str(column["name"])] = {
                "description": (f"{column['type']} column in {reference} ({details})."),
                "aliases": [_humanize(str(column["name"]))],
            }
        tables[key] = {
            "description": f"Database table {reference}.",
            "aliases": [_humanize(table_name)],
            "columns": columns,
        }
    return SemanticLayer.model_validate(
        {
            "version": 1,
            "tables": tables,
            "metrics": {},
            "terms": {},
        }
    )


def generate_privacy_policy(
    selected_tables: list[dict],
    *,
    default_schema: str,
) -> PrivacyPolicy:
    allowed_tables = []
    denied_columns = []
    masks = {}
    restricted_terms = {}

    for table in selected_tables:
        table_reference = _table_reference(table)
        allowed_tables.append(table_reference)
        for column in table.get("columns", []):
            column_name = str(column["name"])
            column_reference = f"{table_reference}.{column_name}"
            if _is_sensitive_deny_column(column_name):
                denied_columns.append(column_reference)
                restricted_terms[column_reference] = [
                    column_name,
                    _humanize(column_name),
                ]
                continue
            strategy = detect_mask_strategy(column_name)
            if strategy:
                masks[column_reference] = strategy

    return PrivacyPolicy.model_validate(
        {
            "version": 1,
            "default_schema": default_schema,
            "tables": {"allow": sorted(allowed_tables), "deny": []},
            "columns": {
                "allow": [],
                "deny": sorted(denied_columns),
                "mask": dict(sorted(masks.items())),
                "restricted_terms": dict(sorted(restricted_terms.items())),
            },
            "masking": {
                "enabled": True,
                "auto_detect": True,
                "allow_aggregates": True,
                "minimum_aggregate_group_size": 2,
                "replacement": "***",
            },
            "question_deny_terms": [],
        }
    )


def _write_private_json(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = (
        json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        temporary_path.chmod(0o600)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def write_generated_configuration(
    *,
    glossary_path: Path,
    privacy_path: Path,
    semantic_layer: SemanticLayer,
    privacy_policy: PrivacyPolicy,
    force: bool,
) -> None:
    existing = [path for path in (glossary_path, privacy_path) if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise DatabaseSetupError(
            f"Refusing to overwrite existing configuration: {names}"
        )
    _write_private_json(glossary_path, semantic_layer)
    _write_private_json(privacy_path, privacy_policy)


def _prompt_choices(label: str, options: list[str]) -> list[str]:
    print(f"{label}:")
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option}")
    raw_value = input("Select comma-separated numbers or names: ").strip()
    if not raw_value:
        raise DatabaseSetupError("A selection is required.")
    selected = []
    for value in (part.strip() for part in raw_value.split(",")):
        if value.isdigit() and 1 <= int(value) <= len(options):
            choice = options[int(value) - 1]
        elif value in options:
            choice = value
        else:
            raise DatabaseSetupError(f"Unknown selection: {value}")
        if choice not in selected:
            selected.append(choice)
    return selected


def _interactive_selection(schema_metadata: list[dict]) -> tuple[list[str], list[str]]:
    schemas = sorted({str(table["schema"]) for table in schema_metadata})
    selected_schemas = _prompt_choices("Accessible schemas", schemas)
    table_options = sorted(
        _table_reference(table)
        for table in schema_metadata
        if str(table["schema"]) in selected_schemas
    )
    selected_tables = _prompt_choices("Accessible tables", table_options)
    return selected_schemas, selected_tables


def _print_connection(report) -> None:
    version = report.server_version.split()[0]
    print(
        f"Connection: PASS (database={report.database}, "
        f"role={report.role}, PostgreSQL={version})"
    )


def _run_check(engine) -> int:
    connection = test_connection(engine)
    metadata = get_schema_metadata(engine)
    role = verify_read_only_role(engine, schema_metadata=metadata)
    _print_connection(connection)
    if not role.is_safe:
        print("Role safety: FAIL")
        for issue in role.issues:
            print(f"  - {issue}")
        return 1
    print("Role safety: PASS")
    print(f"Accessible application tables: {len(metadata)}")
    return 0


def _run_validate(engine) -> int:
    report = validate_database_configuration(engine)
    if not report.is_valid:
        print("Configuration validation: FAIL")
        for issue in report.issues:
            print(f"  - {issue}")
        return 1
    print("Configuration validation: PASS")
    return 0


def _run_configure(engine, args) -> int:
    connection = test_connection(engine)
    metadata = get_schema_metadata(engine)
    role = verify_read_only_role(engine, schema_metadata=metadata)
    _print_connection(connection)
    if not role.is_safe:
        raise DatabaseSetupError(
            "The connected PostgreSQL role is not safely read-only."
        )

    schemas = args.schema
    tables = args.table
    if not tables and not args.all_tables:
        if not sys.stdin.isatty():
            raise DatabaseSetupError(
                "Non-interactive configuration requires --table or --all-tables."
            )
        schemas, tables = _interactive_selection(metadata)

    selected = select_allowed_tables(
        metadata,
        schemas=schemas,
        tables=tables,
        all_tables=args.all_tables,
    )
    selected_schemas = sorted({str(table["schema"]) for table in selected})
    default_schema = args.default_schema or (
        "public" if "public" in selected_schemas else selected_schemas[0]
    )
    if default_schema not in selected_schemas:
        raise DatabaseSetupError(
            "The default schema must contain at least one selected table."
        )

    semantic_layer = generate_semantic_layer(
        selected,
        default_schema=default_schema,
    )
    privacy_policy = generate_privacy_policy(
        selected,
        default_schema=default_schema,
    )
    validation = validate_configuration_references(
        privacy_policy,
        semantic_layer,
        metadata,
    )
    if not validation.is_valid:
        raise DatabaseSetupError("Generated configuration did not validate.")
    selected_references = {_table_reference(table) for table in selected}
    selected_role = verify_read_only_role(
        engine,
        schema_metadata=metadata,
        required_tables=selected_references,
    )
    if not selected_role.is_safe:
        raise DatabaseSetupError(
            "The connected role cannot safely read every selected table."
        )

    write_generated_configuration(
        glossary_path=args.glossary_output,
        privacy_path=args.privacy_output,
        semantic_layer=semantic_layer,
        privacy_policy=privacy_policy,
        force=args.force,
    )
    print("Role safety: PASS")
    print("Allowed tables:")
    for reference in sorted(selected_references):
        print(f"  - {reference}")
    print(f"Glossary: {args.glossary_output}")
    print(f"Privacy policy: {args.privacy_output}")
    print("Configuration validation: PASS")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely onboard and validate a PostgreSQL database."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Test the connection and database role.")
    commands.add_parser(
        "validate",
        help="Validate the active glossary and privacy policy against PostgreSQL.",
    )
    configure = commands.add_parser(
        "configure",
        help="Select tables and generate initial configuration files.",
    )
    configure.add_argument(
        "--schema",
        action="append",
        default=[],
        help="Allowed schema; repeat for multiple schemas.",
    )
    configure.add_argument(
        "--table",
        action="append",
        default=[],
        help="Allowed schema-qualified table; repeat for multiple tables.",
    )
    configure.add_argument(
        "--all-tables",
        action="store_true",
        help="Select all tables from explicitly supplied --schema values.",
    )
    configure.add_argument("--default-schema")
    configure.add_argument(
        "--glossary-output",
        type=Path,
        default=Path("semantic_layer.generated.json"),
    )
    configure.add_argument(
        "--privacy-output",
        type=Path,
        default=Path("privacy_policy.generated.json"),
    )
    configure.add_argument(
        "--force",
        action="store_true",
        help="Replace existing output files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _build_parser().parse_args(argv)
    engine = None
    try:
        engine = get_engine()
        if args.command == "check":
            return _run_check(engine)
        if args.command == "validate":
            return _run_validate(engine)
        return _run_configure(engine, args)
    except (DatabaseAssuranceError, DatabaseSetupError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        get_engine.cache_clear()


if __name__ == "__main__":
    raise SystemExit(main())
