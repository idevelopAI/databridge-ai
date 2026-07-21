from ambiguity import detect_ambiguity


def test_asks_for_salary_basis_before_calling_the_agent():
    result = detect_ambiguity("What is the average salary?", "en")

    assert result is not None
    assert result.code == "compensation_basis"
    assert "gross annual salary" in result.question


def test_accepts_explicit_salary_basis():
    assert detect_ambiguity("What is the average annual gross salary?", "en") is None


def test_asks_for_exact_date_range():
    result = detect_ambiguity("Which projects changed recently?", "en")

    assert result is not None
    assert result.code == "date_range"


def test_asks_for_aggregation_type():
    result = detect_ambiguity("Project data by department", "en")

    assert result is not None
    assert result.code == "aggregation"


def test_asks_for_unspecified_department_in_german():
    result = detect_ambiguity("Wer arbeitet in meiner Abteilung?", "de")

    assert result is not None
    assert result.code == "department"
    assert result.question == "Welche Abteilung meinst du?"


def test_clear_question_does_not_require_clarification():
    assert detect_ambiguity("Wie viele aktive Projekte gibt es?", "de") is None
