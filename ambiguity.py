import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Clarification:
    code: str
    question: str


COMPENSATION_TERMS = (
    "salary",
    "salaries",
    "pay",
    "wage",
    "wages",
    "earn",
    "gehalt",
    "gehaelter",
    "gehälter",
    "lohn",
    "loehne",
    "löhne",
    "verdien",
)
COMPENSATION_QUALIFIERS = (
    "annual",
    "yearly",
    "monthly",
    "hourly",
    "gross",
    "net",
    "jahr",
    "monat",
    "stunde",
    "brutto",
    "netto",
)
VAGUE_PERIODS = (
    "recent",
    "recently",
    "latest period",
    "last period",
    "current period",
    "lately",
    "in letzter zeit",
    "letzter zeitraum",
    "aktueller zeitraum",
    "kürzlich",
    "kuerzlich",
)
GROUPING_MARKERS = (
    "by department",
    "per department",
    "across departments",
    "pro abteilung",
    "nach abteilung",
    "je abteilung",
)
AGGREGATION_MARKERS = (
    "average",
    "mean",
    "total",
    "sum",
    "count",
    "how many",
    "highest",
    "lowest",
    "maximum",
    "minimum",
    "list",
    "show",
    "which",
    "who",
    "durchschnitt",
    "gesamt",
    "summe",
    "anzahl",
    "wie viele",
    "höchst",
    "hoechst",
    "niedrig",
    "liste",
    "zeige",
    "welche",
    "wer",
)
UNSPECIFIED_DEPARTMENTS = (
    "my department",
    "our department",
    "the department",
    "meine abteilung",
    "meiner abteilung",
    "unsere abteilung",
    "unserer abteilung",
    "der abteilung",
)


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _contains_any(value: str, candidates: tuple[str, ...]) -> bool:
    return any(candidate in value for candidate in candidates)


def detect_ambiguity(
    question: str,
    language: Literal["de", "en"],
) -> Clarification | None:
    normalized = _normalize(question)

    if _contains_any(normalized, COMPENSATION_TERMS) and not _contains_any(
        normalized, COMPENSATION_QUALIFIERS
    ):
        text = (
            "Meinst du das Bruttojahresgehalt, das Monatsgehalt oder das Nettogehalt?"
            if language == "de"
            else "Do you mean gross annual salary, monthly salary, or net salary?"
        )
        return Clarification("compensation_basis", text)

    if _contains_any(normalized, VAGUE_PERIODS):
        text = (
            "Welchen genauen Zeitraum soll ich verwenden?"
            if language == "de"
            else "Which exact date range should I use?"
        )
        return Clarification("date_range", text)

    if _contains_any(normalized, GROUPING_MARKERS) and not _contains_any(
        normalized, AGGREGATION_MARKERS
    ):
        text = (
            "Soll ich je Abteilung eine Liste, eine Anzahl, eine Summe oder einen "
            "Durchschnitt berechnen?"
            if language == "de"
            else (
                "For each department, should I return a list, count, total, or average?"
            )
        )
        return Clarification("aggregation", text)

    if _contains_any(normalized, UNSPECIFIED_DEPARTMENTS):
        text = (
            "Welche Abteilung meinst du?"
            if language == "de"
            else "Which department do you mean?"
        )
        return Clarification("department", text)

    return None
