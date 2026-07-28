from unittest.mock import MagicMock, Mock

import pytest

from database_assurance import (
    DatabaseAssuranceError,
    verify_read_only_role,
)
from database_assurance import (
    test_connection as inspect_connection,
)


class MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row


def postgres_engine(connection):
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.dialect.identifier_preparer.quote_schema.side_effect = lambda value: (
        f'"{value}"'
    )
    engine.dialect.identifier_preparer.quote.side_effect = lambda value: f'"{value}"'
    engine.connect.return_value.__enter__.return_value = connection
    return engine


def secure_role_row():
    return {
        "rolname": "report_reader",
        "rolsuper": False,
        "rolcreaterole": False,
        "rolcreatedb": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "transaction_read_only": True,
        "default_transaction_read_only": True,
        "database_create": False,
    }


def test_connection_returns_only_safe_identity_metadata():
    connection = Mock()
    connection.execute.return_value = MappingResult(
        {
            "database": "analytics",
            "role": "report_reader",
            "server_version": "15.8",
        }
    )

    report = inspect_connection(postgres_engine(connection))

    assert report.database == "analytics"
    assert report.role == "report_reader"
    assert report.server_version == "15.8"


def test_connection_rejects_non_postgresql_engine():
    engine = Mock()
    engine.dialect.name = "sqlite"

    with pytest.raises(DatabaseAssuranceError, match="requires PostgreSQL"):
        inspect_connection(engine)


def test_secure_role_has_no_issues():
    connection = Mock()
    connection.execute.return_value = MappingResult(secure_role_row())

    report = verify_read_only_role(
        postgres_engine(connection),
        schema_metadata=[],
    )

    assert report.role == "report_reader"
    assert report.is_safe is True


def test_elevated_role_and_writable_defaults_are_rejected():
    connection = Mock()
    row = secure_role_row()
    row.update(
        {
            "rolsuper": True,
            "transaction_read_only": False,
            "default_transaction_read_only": False,
        }
    )
    connection.execute.return_value = MappingResult(row)

    report = verify_read_only_role(
        postgres_engine(connection),
        schema_metadata=[],
    )

    assert report.is_safe is False
    assert "role is a superuser" in report.issues
    assert "current transaction is not read-only" in report.issues
    assert "default_transaction_read_only is not enabled" in report.issues


def test_role_checks_schema_and_table_privileges():
    connection = Mock()
    connection.execute.side_effect = [
        MappingResult(secure_role_row()),
        Mock(scalar_one=Mock(return_value=False)),
        MappingResult(
            {
                "can_select": True,
                "can_insert": False,
                "can_update": False,
                "can_delete": False,
                "can_truncate": False,
                "can_trigger": False,
            }
        ),
    ]
    metadata = [
        {
            "schema": "reporting",
            "name": "orders",
            "columns": [],
            "foreign_keys": [],
        }
    ]

    report = verify_read_only_role(
        postgres_engine(connection),
        schema_metadata=metadata,
        required_tables={"reporting.orders"},
    )

    assert report.is_safe is True
