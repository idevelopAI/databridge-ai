from unsafe_intent import detect_unsafe_intent


def test_rejects_english_database_modification():
    result = detect_unsafe_intent("Delete all employees", "en")

    assert result is not None
    assert result.code == "unsafe_intent"
    assert "read-only" in result.message


def test_rejects_german_database_modification():
    result = detect_unsafe_intent("Lösche alle Mitarbeiter", "de")

    assert result is not None
    assert result.code == "unsafe_intent"
    assert "Leseabfragen" in result.message


def test_allows_question_about_historical_status():
    assert detect_unsafe_intent("Which projects were deleted last year?", "en") is None
