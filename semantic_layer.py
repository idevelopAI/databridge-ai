import os
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SemanticEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)


class TableSemantic(SemanticEntry):
    columns: dict[str, SemanticEntry] = Field(default_factory=dict)


class MetricSemantic(SemanticEntry):
    expression: str = Field(min_length=1)
    tables: list[str] = Field(min_length=1)


class TermSemantic(SemanticEntry):
    condition: str = Field(min_length=1)
    tables: list[str] = Field(min_length=1)


class SemanticLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    tables: dict[str, TableSemantic]
    metrics: dict[str, MetricSemantic] = Field(default_factory=dict)
    terms: dict[str, TermSemantic] = Field(default_factory=dict)


def _semantic_layer_path() -> Path:
    configured_path = os.environ.get("SEMANTIC_LAYER_PATH")
    if configured_path:
        return Path(configured_path)
    return Path(__file__).with_name("semantic_layer.json")


@lru_cache(maxsize=1)
def get_semantic_layer() -> SemanticLayer:
    try:
        return SemanticLayer.model_validate_json(
            _semantic_layer_path().read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise RuntimeError("The business glossary could not be loaded.") from exc


def get_semantic_layer_data() -> dict:
    return get_semantic_layer().model_dump(mode="json")


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _matches(question: str, names: list[str]) -> bool:
    normalized_question = f" {_normalize(question)} "
    return any(
        f" {_normalize(name)} " in normalized_question
        for name in names
        if _normalize(name)
    )


def semantic_context_for_question(question: str) -> dict:
    layer = get_semantic_layer()
    matched_tables: dict[str, dict] = {}
    matched_metrics: dict[str, dict] = {}
    matched_terms: dict[str, dict] = {}
    referenced_tables: set[str] = set()

    for name, metric in layer.metrics.items():
        if _matches(question, [name.replace("_", " "), *metric.aliases]):
            matched_metrics[name] = metric.model_dump(mode="json")
            referenced_tables.update(metric.tables)

    for name, term in layer.terms.items():
        if _matches(question, [name.replace("_", " "), *term.aliases]):
            matched_terms[name] = term.model_dump(mode="json")
            referenced_tables.update(term.tables)

    for table_name, table in layer.tables.items():
        table_names = [table_name.replace("_", " "), *table.aliases]
        column_names = [
            candidate
            for column_name, column in table.columns.items()
            for candidate in [column_name.replace("_", " "), *column.aliases]
        ]
        if table_name in referenced_tables or _matches(
            question, [*table_names, *column_names]
        ):
            matched_tables[table_name] = table.model_dump(mode="json")

    return {
        "tables": matched_tables,
        "metrics": matched_metrics,
        "terms": matched_terms,
    }


def clear_semantic_layer_cache() -> None:
    get_semantic_layer.cache_clear()
