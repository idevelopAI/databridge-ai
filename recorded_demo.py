import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from evaluation.models import EvaluationCase, load_dataset
from observability import AgentTelemetry
from sql_tools import execute_read_only_query

DATASET_PATH = Path(__file__).with_name("evaluation") / "cases.json"

QUESTION_ALIASES = {
    "wer verdient am meisten im engineering": "en_engineering_top_earner",
    "who earns the most in engineering": "en_engineering_top_earner",
    "wie hoch ist das durchschnittliche gehalt pro abteilung": (
        "en_average_salary_by_department"
    ),
    "wie hoch ist das durchschnittliche bruttojahresgehalt pro abteilung": (
        "en_average_salary_by_department"
    ),
    "what is the average annual gross salary by department": (
        "en_average_salary_by_department"
    ),
    "what is the average salary by department": "en_average_salary_by_department",
    "welche projekte haben das höchste budget": "de_projekte_nach_budget",
    "which projects have the highest budget": "de_projekte_nach_budget",
    "liste die mitarbeiter im engineering nach bruttojahresgehalt absteigend": (
        "en_engineering_employees"
    ),
    "list engineering employees from highest to lowest annual gross salary": (
        "en_engineering_employees"
    ),
}


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _current_question(prompt: str) -> str:
    marker = "Current question:\n"
    if marker not in prompt:
        return prompt.strip()
    return prompt.split(marker, 1)[1].split("\n\nReturn the final answer", 1)[0].strip()


@lru_cache(maxsize=1)
def _cases() -> tuple[dict[str, EvaluationCase], dict[str, EvaluationCase]]:
    dataset = load_dataset(DATASET_PATH)
    by_id = {case.id: case for case in dataset.cases}
    by_question = {_normalize(case.question): case for case in dataset.cases}
    for alias, case_id in QUESTION_ALIASES.items():
        by_question[alias] = by_id[case_id]
    return by_id, by_question


def _follow_up_case(
    current_question: str,
    full_prompt: str,
    by_id: dict[str, EvaluationCase],
) -> EvaluationCase | None:
    current = _normalize(current_question)
    has_basis = any(
        term in current
        for term in (
            "annual",
            "gross",
            "yearly",
            "brutto",
            "jahr",
            "monatsgehalt",
            "monthly",
            "netto",
            "net salary",
        )
    )
    if not has_basis:
        return None

    context = _normalize(full_prompt)
    if "durchschnittliche gehalt pro abteilung" in context:
        return by_id["en_average_salary_by_department"]
    if "average salary by department" in context:
        return by_id["en_average_salary_by_department"]
    if "am meisten im engineering" in context:
        return by_id["en_engineering_top_earner"]
    if "most in engineering" in context:
        return by_id["en_engineering_top_earner"]
    return None


class RecordedDemoAgent:
    def __init__(self, *, mask_results: bool = True) -> None:
        self.mask_results = mask_results

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("input", ""))
        question = _current_question(prompt)
        by_id, by_question = _cases()
        case = by_question.get(_normalize(question))
        if case is None:
            case = _follow_up_case(question, prompt, by_id)

        telemetry = AgentTelemetry()
        if case is None:
            german = "Return the final answer in German." in prompt
            output = (
                "Dieses aufgezeichnete Demo-Szenario kennt diese Frage noch nicht."
                if german
                else "This recorded demo scenario does not include that question."
            )
            return {"output": output, "telemetry": telemetry}

        execution = execute_read_only_query(
            case.expected_sql,
            mask_results=self.mask_results,
        )
        if "error" in execution:
            return {
                "output": "Die Demo-Abfrage wurde abgelehnt.",
                "telemetry": telemetry,
            }

        german = "Return the final answer in German." in prompt
        output = "Das verifizierte Ergebnis ist" if german else "The verified result is"
        return {"output": output, "telemetry": telemetry}


def build_recorded_demo_agent(*, mask_results: bool = True) -> RecordedDemoAgent:
    return RecordedDemoAgent(mask_results=mask_results)
