from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExpectedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str] = Field(min_length=1)
    rows: list[list[Any]]
    ordered: bool = True


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    language: Literal["de", "en"]
    question: str = Field(min_length=1)
    expected_sql: str = Field(min_length=1)
    expected: ExpectedResult
    tags: list[str] = Field(default_factory=list)


class UnsafeCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    sql: str = Field(min_length=1)


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    fixture: str = Field(min_length=1)
    cases: list[EvaluationCase] = Field(min_length=30, max_length=50)
    unsafe_cases: list[UnsafeCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self):
        identifiers = [case.id for case in self.cases]
        identifiers.extend(case.id for case in self.unsafe_cases)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Evaluation case IDs must be unique.")
        return self


def load_dataset(path: Path) -> EvaluationDataset:
    try:
        return EvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("The evaluation dataset could not be loaded.") from exc
