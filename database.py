from functools import lru_cache

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from config import get_database_url

SYSTEM_SCHEMAS = {"information_schema", "pg_catalog"}


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_database_url(), pool_pre_ping=True)


def _application_schemas(inspector) -> list[str]:
    return sorted(
        schema_name
        for schema_name in inspector.get_schema_names()
        if schema_name not in SYSTEM_SCHEMAS and not schema_name.startswith("pg_")
    )


def get_schema_metadata(
    engine: Engine | None = None,
    *,
    schemas: list[str] | None = None,
) -> list[dict]:
    active_engine = engine or get_engine()
    inspector = inspect(active_engine)
    if active_engine.dialect.name == "postgresql":
        available_schemas = _application_schemas(inspector)
        schema_names = schemas if schemas is not None else available_schemas
        unknown_schemas = sorted(set(schema_names) - set(available_schemas))
        if unknown_schemas:
            raise RuntimeError("One or more configured database schemas do not exist.")
    else:
        schema_names = [None]
    tables = []

    for schema_name in schema_names:
        for table_name in sorted(inspector.get_table_names(schema=schema_name)):
            primary_keys = set(
                inspector.get_pk_constraint(table_name, schema=schema_name).get(
                    "constrained_columns", []
                )
            )
            inspected_foreign_keys = inspector.get_foreign_keys(
                table_name, schema=schema_name
            )
            foreign_key_columns = {
                column
                for foreign_key in inspected_foreign_keys
                for column in foreign_key.get("constrained_columns", [])
            }
            columns = []

            for column in inspector.get_columns(table_name, schema=schema_name):
                column_name = column["name"]
                flags = []
                if column_name in primary_keys:
                    flags.append("PK")
                if column_name in foreign_key_columns:
                    flags.append("FK")

                columns.append(
                    {
                        "name": column_name,
                        "type": str(column["type"]),
                        "nullable": bool(column.get("nullable", True)),
                        "flags": flags,
                    }
                )

            foreign_keys = []
            for foreign_key in inspected_foreign_keys:
                foreign_keys.append(
                    {
                        "columns": foreign_key.get("constrained_columns", []),
                        "referred_schema": foreign_key.get("referred_schema"),
                        "referred_table": foreign_key.get("referred_table"),
                        "referred_columns": foreign_key.get("referred_columns", []),
                    }
                )

            tables.append(
                {
                    "schema": schema_name or "",
                    "name": table_name,
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                }
            )

    return tables
