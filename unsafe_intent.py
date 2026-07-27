import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class UnsafeIntent:
    code: str
    message: str


ENGLISH_PATTERNS = (
    r"^\s*(?:please\s+)?(?:delete|drop|truncate|update|insert|alter|create|grant|revoke)\b",
    r"^\s*(?:can|could|would)\s+you\s+(?:delete|drop|truncate|update|insert|alter|create)\b",
    r"\b(?:delete|remove)\s+(?:all|every)\s+(?:row|record|employee|project|department)",
)
GERMAN_PATTERNS = (
    r"^\s*(?:bitte\s+)?(?:lösche|loesche|entferne|aktualisiere|ändere|aendere|erstelle|leere)\b",
    r"^\s*(?:bitte\s+)?(?:füge|fuege)\b.+\bhinzu\b",
    r"^\s*kannst\s+du\b.+\b(?:löschen|loeschen|entfernen|ändern|aendern)\b",
    r"\b(?:lösche|loesche|entferne)\s+(?:alle|jeden|sämtliche|saemtliche)\b",
)


def detect_unsafe_intent(
    question: str,
    language: Literal["de", "en"],
) -> UnsafeIntent | None:
    patterns = GERMAN_PATTERNS + ENGLISH_PATTERNS
    if not any(re.search(pattern, question.casefold()) for pattern in patterns):
        return None

    message = (
        "Datenbankänderungen sind nicht erlaubt. DataBridge AI führt nur "
        "Leseabfragen aus."
        if language == "de"
        else "Database modifications are not allowed. DataBridge AI only runs "
        "read-only queries."
    )
    return UnsafeIntent("unsafe_intent", message)
