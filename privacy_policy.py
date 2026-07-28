import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import sqlglot
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlglot import exp
from sqlglot.errors import ParseError

MaskStrategy = Literal["email", "identifier", "phone", "salary"]
COLLECTION_AGGREGATE_NAMES = {
    "array_agg",
    "json_agg",
    "json_object_agg",
    "jsonb_agg",
    "jsonb_object_agg",
    "string_agg",
    "xmlagg",
}
COLLECTION_AGGREGATE_TYPES = (exp.ArrayAgg, exp.JSONArrayAgg, exp.GroupConcat)
SAFE_MASKED_AGGREGATE_TYPES = (exp.Avg, exp.Count, exp.Sum)


class AccessRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)


class ColumnRules(AccessRules):
    mask: dict[str, MaskStrategy] = Field(default_factory=dict)
    restricted_terms: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def restricted_terms_reference_denied_columns(self):
        denied = {_identifier(value) for value in self.deny}
        unknown = {
            _identifier(value)
            for value in self.restricted_terms
            if _identifier(value) not in denied
        }
        if unknown:
            raise ValueError("Restricted terms must reference denied columns.")
        return self


class MaskingRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    auto_detect: bool = True
    allow_aggregates: bool = True
    minimum_aggregate_group_size: int = Field(default=2, ge=2)
    replacement: str = Field(default="***", min_length=1, max_length=32)


class PrivacyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    default_schema: str = Field(default="public", min_length=1)
    tables: AccessRules
    columns: ColumnRules
    masking: MaskingRules = Field(default_factory=MaskingRules)
    question_deny_terms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_access_lists(self):
        for rules in (self.tables, self.columns):
            allowed = {_identifier(value) for value in rules.allow}
            denied = {_identifier(value) for value in rules.deny}
            if allowed & denied:
                raise ValueError("Privacy allowlists and denylists must not overlap.")
        table_references = [*self.tables.allow, *self.tables.deny]
        if any(reference.count(".") != 1 for reference in table_references):
            raise ValueError("Privacy table references must be schema-qualified.")
        column_references = [
            *self.columns.allow,
            *self.columns.deny,
            *self.columns.mask,
            *self.columns.restricted_terms,
        ]
        if any(reference.count(".") != 2 for reference in column_references):
            raise ValueError("Privacy column references must be schema-qualified.")
        return self


@dataclass(frozen=True)
class PrivacyDecision:
    is_allowed: bool
    reason_code: str = ""
    message: str = ""


def _identifier(value: str) -> str:
    return value.strip().casefold()


def _normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def get_privacy_policy_path() -> Path:
    configured_path = os.environ.get("PRIVACY_POLICY_PATH")
    if configured_path:
        return Path(configured_path)
    return Path(__file__).with_name("privacy_policy.json")


def load_privacy_policy(path: Path) -> PrivacyPolicy:
    try:
        return PrivacyPolicy.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise RuntimeError("The privacy policy could not be loaded.") from exc


@lru_cache(maxsize=1)
def get_privacy_policy() -> PrivacyPolicy:
    return load_privacy_policy(get_privacy_policy_path())


def get_privacy_policy_data() -> dict[str, Any]:
    return get_privacy_policy().model_dump(mode="json")


def clear_privacy_policy_cache() -> None:
    get_privacy_policy.cache_clear()


def restricted_question_reason(question: str) -> str | None:
    policy = get_privacy_policy()
    normalized = f" {_normalize_text(question)} "

    restricted_phrases = [
        term for terms in policy.columns.restricted_terms.values() for term in terms
    ]
    restricted_phrases.extend(policy.tables.deny)
    restricted_phrases.extend(policy.question_deny_terms)
    for phrase in restricted_phrases:
        candidate = _normalize_text(phrase.replace("_", " "))
        if candidate and f" {candidate} " in normalized:
            return "restricted_field"
    return None


def _parse_sql(query: str) -> exp.Expression:
    try:
        statement = sqlglot.parse_one(query, read="postgres")
    except ParseError as exc:
        raise ValueError("SQL could not be inspected by the privacy policy.") from exc
    if statement is None:
        raise ValueError("SQL could not be inspected by the privacy policy.")
    return statement


def _qualified_table_name(table: exp.Table, default_schema: str) -> str:
    table_name = _identifier(table.name)
    schema_name = _identifier(table.db) or _identifier(default_schema)
    catalog_name = _identifier(table.catalog)
    if catalog_name:
        return f"{catalog_name}.{schema_name}.{table_name}"
    return f"{schema_name}.{table_name}"


def _table_context(
    statement: exp.Expression,
    default_schema: str,
) -> tuple[dict[str, str], set[str]]:
    cte_names = {
        _identifier(cte.alias_or_name)
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    aliases: dict[str, str] = {}
    tables: set[str] = set()
    for table in statement.find_all(exp.Table):
        table_name = _identifier(table.name)
        if table_name in cte_names:
            continue
        qualified_name = _qualified_table_name(table, default_schema)
        tables.add(qualified_name)
        aliases[_identifier(table.alias_or_name)] = qualified_name
        aliases[table_name] = qualified_name
        aliases[qualified_name] = qualified_name
    return aliases, tables


def _column_reference(
    column: exp.Column,
    aliases: dict[str, str],
    tables: set[str],
) -> str | None:
    column_name = _identifier(column.name)
    qualifier = _identifier(column.table)
    if qualifier:
        return f"{aliases.get(qualifier, qualifier)}.{column_name}"
    if len(tables) == 1:
        return f"{next(iter(tables))}.{column_name}"
    return None


def _function_name(function: exp.Func) -> str:
    if function.name:
        return _identifier(function.name)
    return _identifier(function.sql(dialect="postgres").split("(", 1)[0])


def _is_collection_aggregate(function: exp.Func) -> bool:
    return isinstance(function, COLLECTION_AGGREGATE_TYPES) or (
        _function_name(function) in COLLECTION_AGGREGATE_NAMES
    )


def _is_whole_row_reference(column: exp.Column, aliases: dict[str, str]) -> bool:
    return not column.table and _identifier(column.name) in aliases


def _mask_strategy_for_column(
    column: exp.Column,
    aliases: dict[str, str],
    tables: set[str],
    policy: PrivacyPolicy,
) -> MaskStrategy | None:
    explicit_masks = {
        _identifier(reference): strategy
        for reference, strategy in policy.columns.mask.items()
    }
    reference = _column_reference(column, aliases, tables)
    if reference and reference in explicit_masks:
        return explicit_masks[reference]
    if policy.masking.auto_detect:
        return _strategy_for_name(column.name)
    return None


def _masked_references(
    expression: exp.Expression,
    aliases: dict[str, str],
    tables: set[str],
    policy: PrivacyPolicy,
) -> set[str]:
    references = set()
    for column in expression.find_all(exp.Column):
        if not _mask_strategy_for_column(column, aliases, tables, policy):
            continue
        reference = _column_reference(column, aliases, tables)
        if reference:
            references.add(reference)
    return references


def _minimum_cohort_references(
    select: exp.Select,
    aliases: dict[str, str],
    tables: set[str],
    minimum_size: int,
) -> set[str]:
    having = select.args.get("having")
    if having is None or having.find(exp.Or):
        return set()

    references = set()
    for comparison_type, inclusive_adjustment in ((exp.GTE, 0), (exp.GT, 1)):
        for comparison in having.find_all(comparison_type):
            count = comparison.this
            threshold = comparison.expression
            if not isinstance(count, exp.Count) or not isinstance(
                threshold, exp.Literal
            ):
                continue
            try:
                threshold_value = int(threshold.this) + inclusive_adjustment
            except (TypeError, ValueError):
                continue
            if threshold_value < minimum_size:
                continue
            for column in count.find_all(exp.Column):
                reference = _column_reference(column, aliases, tables)
                if reference:
                    references.add(reference)
    return references


def _validate_masked_aggregates(
    statement: exp.Expression,
    aliases: dict[str, str],
    tables: set[str],
    policy: PrivacyPolicy,
) -> PrivacyDecision | None:
    for function in statement.find_all(exp.Func):
        if _is_collection_aggregate(function):
            return PrivacyDecision(
                False,
                "restricted_column",
                "Collection aggregates are blocked by the privacy policy.",
            )

    if any(
        _is_whole_row_reference(column, aliases)
        for column in statement.find_all(exp.Column)
    ):
        return PrivacyDecision(
            False,
            "restricted_column",
            "Whole-row values are blocked by the privacy policy.",
        )

    for select in statement.find_all(exp.Select):
        cohort_references = _minimum_cohort_references(
            select,
            aliases,
            tables,
            policy.masking.minimum_aggregate_group_size,
        )
        for projection in select.expressions:
            aggregates = list(projection.find_all(exp.AggFunc))
            masked_references = _masked_references(projection, aliases, tables, policy)
            if not aggregates or not masked_references:
                continue
            if not policy.masking.allow_aggregates or not all(
                isinstance(aggregate, SAFE_MASKED_AGGREGATE_TYPES)
                for aggregate in aggregates
            ):
                return PrivacyDecision(
                    False,
                    "restricted_column",
                    "The aggregate requests a masked field.",
                )
            if all(isinstance(aggregate, exp.Count) for aggregate in aggregates):
                continue
            aggregate_references = {
                reference
                for aggregate in aggregates
                if not isinstance(aggregate, exp.Count)
                for reference in _masked_references(aggregate, aliases, tables, policy)
            }
            if not aggregate_references <= cohort_references:
                return PrivacyDecision(
                    False,
                    "aggregate_cohort",
                    "The aggregate does not enforce the minimum cohort size.",
                )
    return None


def validate_sql_privacy(query: str) -> PrivacyDecision:
    policy = get_privacy_policy()
    try:
        statement = _parse_sql(query)
    except ValueError:
        return PrivacyDecision(
            False,
            "uninspectable_sql",
            "The query could not be inspected by the privacy policy.",
        )

    aliases, tables = _table_context(statement, policy.default_schema)
    allowed_tables = {_identifier(value) for value in policy.tables.allow}
    denied_tables = {_identifier(value) for value in policy.tables.deny}
    if tables & denied_tables or (allowed_tables and not tables <= allowed_tables):
        return PrivacyDecision(
            False,
            "restricted_table",
            "The query requests a table restricted by the privacy policy.",
        )

    aggregate_decision = _validate_masked_aggregates(statement, aliases, tables, policy)
    if aggregate_decision is not None:
        return aggregate_decision

    allowed_columns = {_identifier(value) for value in policy.columns.allow}
    denied_columns = {_identifier(value) for value in policy.columns.deny}
    wildcard_projection = any(
        projection.find(exp.Star) and not projection.find(exp.AggFunc)
        for select in statement.find_all(exp.Select)
        for projection in select.expressions
    )
    if (allowed_columns or denied_columns) and wildcard_projection:
        return PrivacyDecision(
            False,
            "wildcard_selection",
            "Wildcard selection is blocked by the privacy policy.",
        )

    for column in statement.find_all(exp.Column):
        reference = _column_reference(column, aliases, tables)
        if reference is None:
            matching_denied = any(
                value.endswith(f".{_identifier(column.name)}")
                for value in denied_columns
            )
            if matching_denied or allowed_columns:
                return PrivacyDecision(
                    False,
                    "restricted_column",
                    "The query requests a column restricted by the privacy policy.",
                )
            continue
        if reference in denied_columns or (
            allowed_columns and reference not in allowed_columns
        ):
            return PrivacyDecision(
                False,
                "restricted_column",
                "The query requests a column restricted by the privacy policy.",
            )

    return PrivacyDecision(True)


def filter_schema_by_policy(schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    policy = get_privacy_policy()
    allowed_tables = {_identifier(value) for value in policy.tables.allow}
    denied_tables = {_identifier(value) for value in policy.tables.deny}
    allowed_columns = {_identifier(value) for value in policy.columns.allow}
    denied_columns = {_identifier(value) for value in policy.columns.deny}
    visible_tables = []

    for table in schema:
        table_name = _identifier(table["name"])
        schema_name = _identifier(
            table.get("schema", policy.default_schema)
        ) or _identifier(policy.default_schema)
        table_reference = f"{schema_name}.{table_name}"
        if table_reference in denied_tables or (
            allowed_tables and table_reference not in allowed_tables
        ):
            continue
        visible_columns = []
        for column in table.get("columns", []):
            reference = f"{table_reference}.{_identifier(column['name'])}"
            if reference in denied_columns or (
                allowed_columns and reference not in allowed_columns
            ):
                continue
            visible_columns.append(column)
        visible_table = dict(table)
        visible_table["columns"] = visible_columns
        visible_tables.append(visible_table)

    return visible_tables


def _strategy_for_name(name: str) -> MaskStrategy | None:
    normalized = _identifier(name)
    if "email" in normalized or "e_mail" in normalized:
        return "email"
    if any(
        token in normalized
        for token in ("phone", "mobile", "telephone", "telefon", "contact_number")
    ):
        return "phone"
    if normalized == "id" or normalized.endswith("_id"):
        return "identifier"
    if any(token in normalized for token in ("salary", "wage", "gehalt", "lohn")):
        return "salary"
    return None


def _final_select(statement: exp.Expression) -> exp.Select | None:
    if isinstance(statement, exp.Select):
        return statement
    return next(statement.find_all(exp.Select), None)


def _projection_mask_strategy(
    projection: exp.Expression,
    output_name: str,
    aliases: dict[str, str],
    tables: set[str],
    policy: PrivacyPolicy,
) -> MaskStrategy | None:
    masked_strategy = None
    for column in projection.find_all(exp.Column):
        strategy = _mask_strategy_for_column(column, aliases, tables, policy)
        if strategy:
            masked_strategy = strategy
            break

    aggregates = list(projection.find_all(exp.AggFunc))
    if masked_strategy and aggregates:
        select = projection.find_ancestor(exp.Select)
        cohort_references = (
            _minimum_cohort_references(
                select,
                aliases,
                tables,
                policy.masking.minimum_aggregate_group_size,
            )
            if select is not None
            else set()
        )
        aggregate_references = {
            reference
            for aggregate in aggregates
            if not isinstance(aggregate, exp.Count)
            for reference in _masked_references(aggregate, aliases, tables, policy)
        }
        if (
            policy.masking.allow_aggregates
            and all(
                isinstance(aggregate, SAFE_MASKED_AGGREGATE_TYPES)
                for aggregate in aggregates
            )
            and (
                all(isinstance(aggregate, exp.Count) for aggregate in aggregates)
                or aggregate_references <= cohort_references
            )
        ):
            return None

    if masked_strategy:
        return masked_strategy

    if policy.masking.auto_detect:
        return _strategy_for_name(output_name)
    return None


def mask_result_rows(
    query: str,
    columns: list[str],
    rows: list[list[Any]],
) -> list[list[Any]]:
    policy = get_privacy_policy()
    if not policy.masking.enabled or not rows:
        return rows

    try:
        statement = _parse_sql(query)
    except ValueError:
        return [[policy.masking.replacement for _ in row] for row in rows]

    aliases, tables = _table_context(statement, policy.default_schema)
    select = _final_select(statement)
    projections = select.expressions if select is not None else []
    mask_indexes = set()
    for index, output_name in enumerate(columns):
        projection = projections[index] if index < len(projections) else None
        strategy = (
            _projection_mask_strategy(
                projection,
                output_name,
                aliases,
                tables,
                policy,
            )
            if projection is not None
            else _strategy_for_name(output_name)
        )
        if strategy:
            mask_indexes.add(index)

    return [
        [
            None
            if value is None
            else policy.masking.replacement
            if index in mask_indexes
            else value
            for index, value in enumerate(row)
        ]
        for row in rows
    ]
