from functools import lru_cache

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_database_url(), pool_pre_ping=True)


def get_schema_metadata(engine: Engine | None = None) -> list[dict]:
    active_engine = engine or get_engine()
    inspector = inspect(active_engine)
    schema_name = "public" if active_engine.dialect.name == "postgresql" else None
    tables = []

    for table_name in sorted(inspector.get_table_names(schema=schema_name)):
        primary_keys = set(
            inspector.get_pk_constraint(table_name, schema=schema_name).get(
                "constrained_columns", []
            )
        )
        foreign_key_columns = {
            column
            for foreign_key in inspector.get_foreign_keys(
                table_name, schema=schema_name
            )
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
        for foreign_key in inspector.get_foreign_keys(table_name, schema=schema_name):
            foreign_keys.append(
                {
                    "columns": foreign_key.get("constrained_columns", []),
                    "referred_table": foreign_key.get("referred_table"),
                    "referred_columns": foreign_key.get("referred_columns", []),
                }
            )

        tables.append(
            {
                "name": table_name,
                "columns": columns,
                "foreign_keys": foreign_keys,
            }
        )

    return tables
