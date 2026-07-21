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
    replacement: str = Field(default="***", min_length=1, max_length=32)


class PrivacyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    tables: AccessRules
    columns: ColumnRules
    masking: MaskingRules = Field(default_factory=MaskingRules)

    @model_validator(mode="after")
    def access_lists_do_not_overlap(self):
        for rules in (self.tables, self.columns):
            allowed = {_identifier(value) for value in rules.allow}
            denied = {_identifier(value) for value in rules.deny}
            if allowed & denied:
                raise ValueError("Privacy allowlists and denylists must not overlap.")
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


def _privacy_policy_path() -> Path:
    configured_path = os.environ.get("PRIVACY_POLICY_PATH")
    if configured_path:
        return Path(configured_path)
    return Path(__file__).with_name("privacy_policy.json")


@lru_cache(maxsize=1)
def get_privacy_policy() -> PrivacyPolicy:
    try:
        return PrivacyPolicy.model_validate_json(
            _privacy_policy_path().read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise RuntimeError("The privacy policy could not be loaded.") from exc


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


def _table_context(statement: exp.Expression) -> tuple[dict[str, str], set[str]]:
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
        tables.add(table_name)
        aliases[_identifier(table.alias_or_name)] = table_name
        aliases[table_name] = table_name
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

    aliases, tables = _table_context(statement)
    allowed_tables = {_identifier(value) for value in policy.tables.allow}
    denied_tables = {_identifier(value) for value in policy.tables.deny}
    if tables & denied_tables or (allowed_tables and not tables <= allowed_tables):
        return PrivacyDecision(
            False,
            "restricted_table",
            "The query requests a table restricted by the privacy policy.",
        )

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
        if table_name in denied_tables or (
            allowed_tables and table_name not in allowed_tables
        ):
            continue
        visible_columns = []
        for column in table.get("columns", []):
            reference = f"{table_name}.{_identifier(column['name'])}"
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
    if policy.masking.allow_aggregates and projection.find(exp.AggFunc):
        return None

    explicit_masks = {
        _identifier(reference): strategy
        for reference, strategy in policy.columns.mask.items()
    }
    for column in projection.find_all(exp.Column):
        reference = _column_reference(column, aliases, tables)
        if reference and reference in explicit_masks:
            return explicit_masks[reference]
        if policy.masking.auto_detect:
            strategy = _strategy_for_name(column.name)
            if strategy:
                return strategy

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

    aliases, tables = _table_context(statement)
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
