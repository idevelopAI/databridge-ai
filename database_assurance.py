from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from database import get_schema_metadata


class DatabaseAssuranceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConnectionReport:
    database: str
    role: str
    server_version: str


@dataclass(frozen=True)
class RoleSecurityReport:
    role: str
    issues: tuple[str, ...]

    @property
    def is_safe(self) -> bool:
        return not self.issues


def _require_postgresql(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        raise DatabaseAssuranceError("Database onboarding requires PostgreSQL.")


def test_connection(engine: Engine) -> ConnectionReport:
    _require_postgresql(engine)
    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT
                            current_database() AS database,
                            current_user AS role,
                            current_setting('server_version') AS server_version
                        """
                    )
                )
                .mappings()
                .one()
            )
    except SQLAlchemyError as exc:
        raise DatabaseAssuranceError(
            "PostgreSQL connection validation failed."
        ) from exc
    return ConnectionReport(
        database=str(row["database"]),
        role=str(row["role"]),
        server_version=str(row["server_version"]),
    )


def _qualified_relation(engine: Engine, schema: str, table: str) -> str:
    preparer = engine.dialect.identifier_preparer
    return f"{preparer.quote_schema(schema)}.{preparer.quote(table)}"


def _role_attribute_issues(row: dict[str, Any]) -> list[str]:
    issues = []
    unsafe_attributes = {
        "rolsuper": "role is a superuser",
        "rolcreaterole": "role can create roles",
        "rolcreatedb": "role can create databases",
        "rolreplication": "role can replicate",
        "rolbypassrls": "role can bypass row-level security",
        "database_create": "role can create database objects",
    }
    for field, message in unsafe_attributes.items():
        if row.get(field):
            issues.append(message)
    if not row.get("transaction_read_only"):
        issues.append("current transaction is not read-only")
    if not row.get("default_transaction_read_only"):
        issues.append("default_transaction_read_only is not enabled")
    return issues


def verify_read_only_role(
    engine: Engine,
    *,
    schema_metadata: list[dict] | None = None,
    required_tables: set[str] | None = None,
) -> RoleSecurityReport:
    _require_postgresql(engine)
    metadata = (
        get_schema_metadata(engine) if schema_metadata is None else schema_metadata
    )
    required = {value.casefold() for value in required_tables or set()}
    issues: list[str] = []

    try:
        with engine.connect() as connection:
            role_row = (
                connection.execute(
                    text(
                        """
                        SELECT
                            role.rolname,
                            role.rolsuper,
                            role.rolcreaterole,
                            role.rolcreatedb,
                            role.rolreplication,
                            role.rolbypassrls,
                            current_setting('transaction_read_only') = 'on'
                                AS transaction_read_only,
                            current_setting('default_transaction_read_only') = 'on'
                                AS default_transaction_read_only,
                            has_database_privilege(
                                current_user,
                                current_database(),
                                'CREATE'
                            ) AS database_create
                        FROM pg_roles AS role
                        WHERE role.rolname = current_user
                        """
                    )
                )
                .mappings()
                .one()
            )
            issues.extend(_role_attribute_issues(dict(role_row)))

            checked_schemas = set()
            for table in metadata:
                schema_name = str(table["schema"])
                table_name = str(table["name"])
                reference = f"{schema_name}.{table_name}"
                if schema_name not in checked_schemas:
                    checked_schemas.add(schema_name)
                    can_create = connection.execute(
                        text(
                            "SELECT has_schema_privilege("
                            "current_user, :schema_name, 'CREATE')"
                        ),
                        {"schema_name": schema_name},
                    ).scalar_one()
                    if can_create:
                        issues.append(
                            f"role can create objects in schema {schema_name}"
                        )

                privileges = (
                    connection.execute(
                        text(
                            """
                            SELECT
                                has_table_privilege(
                                    current_user, :table_name, 'SELECT'
                                ) AS can_select,
                                has_table_privilege(
                                    current_user, :table_name, 'INSERT'
                                ) AS can_insert,
                                has_table_privilege(
                                    current_user, :table_name, 'UPDATE'
                                ) AS can_update,
                                has_table_privilege(
                                    current_user, :table_name, 'DELETE'
                                ) AS can_delete,
                                has_table_privilege(
                                    current_user, :table_name, 'TRUNCATE'
                                ) AS can_truncate,
                                has_table_privilege(
                                    current_user, :table_name, 'TRIGGER'
                                ) AS can_trigger
                            """
                        ),
                        {
                            "table_name": _qualified_relation(
                                engine, schema_name, table_name
                            )
                        },
                    )
                    .mappings()
                    .one()
                )
                if any(
                    privileges[field]
                    for field in (
                        "can_insert",
                        "can_update",
                        "can_delete",
                        "can_truncate",
                        "can_trigger",
                    )
                ):
                    issues.append(f"role has write privileges on table {reference}")
                if reference.casefold() in required and not privileges["can_select"]:
                    issues.append(f"role cannot select configured table {reference}")
    except SQLAlchemyError as exc:
        raise DatabaseAssuranceError("PostgreSQL role validation failed.") from exc

    return RoleSecurityReport(
        role=str(role_row["rolname"]),
        issues=tuple(sorted(set(issues))),
    )
