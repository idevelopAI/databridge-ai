from configuration_validation import validate_configuration_references
from privacy_policy import PrivacyPolicy
from semantic_layer import SemanticLayer


def policy(**column_rules):
    return PrivacyPolicy.model_validate(
        {
            "version": 1,
            "default_schema": "public",
            "tables": {"allow": ["public.employees"], "deny": []},
            "columns": {
                "allow": column_rules.get("allow", []),
                "deny": column_rules.get("deny", []),
                "mask": column_rules.get("mask", {}),
                "restricted_terms": column_rules.get("restricted_terms", {}),
            },
            "masking": {},
        }
    )


def semantic_layer(*column_names):
    return SemanticLayer.model_validate(
        {
            "version": 1,
            "tables": {
                "employees": {
                    "description": "Employees.",
                    "aliases": [],
                    "columns": {
                        name: {"description": "Configured column.", "aliases": []}
                        for name in column_names
                    },
                }
            },
            "metrics": {
                "employee_count": {
                    "description": "Employee count.",
                    "aliases": [],
                    "expression": "COUNT(employees.id)",
                    "tables": ["employees"],
                }
            },
            "terms": {},
        }
    )


def metadata():
    return [
        {
            "schema": "public",
            "name": "employees",
            "columns": [{"name": "id"}, {"name": "email"}],
            "foreign_keys": [],
        }
    ]


def test_valid_configuration_matches_live_schema():
    report = validate_configuration_references(
        policy(mask={"public.employees.email": "email"}),
        semantic_layer("id", "email"),
        metadata(),
    )

    assert report.is_valid is True


def test_missing_privacy_column_is_reported():
    report = validate_configuration_references(
        policy(deny=["public.employees.deleted_secret"]),
        semantic_layer("id"),
        metadata(),
    )

    assert report.is_valid is False
    assert report.issues == (
        "configured column does not exist: public.employees.deleted_secret",
    )


def test_missing_glossary_and_metric_columns_are_reported():
    layer = semantic_layer("id", "removed_column")
    layer.metrics["employee_count"].expression = "COUNT(employees.removed_id)"

    report = validate_configuration_references(
        policy(),
        layer,
        metadata(),
    )

    assert "glossary column does not exist: employees.removed_column" in report.issues
    assert (
        "metric employee_count references a missing or ambiguous column: "
        "employees.removed_id"
    ) in report.issues
