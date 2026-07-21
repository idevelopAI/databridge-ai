from pathlib import Path

from evaluation.comparison import compare_execution
from evaluation.models import ExpectedResult, load_dataset
from evaluation.run import _offline_case


def test_evaluation_dataset_has_bilingual_coverage():
    dataset = load_dataset(Path("evaluation/cases.json"))

    assert len(dataset.cases) == 40
    assert len(dataset.unsafe_cases) == 12
    assert {case.language for case in dataset.cases} == {"de", "en"}


def test_result_comparison_accepts_numeric_driver_differences():
    expected = ExpectedResult(
        columns=["average_salary"],
        rows=[[87166.67]],
    )
    execution = {
        "columns": ["different_alias"],
        "rows": [[87166.670001]],
    }

    result = compare_execution(execution, expected)

    assert result.equivalent is True


def test_result_comparison_honors_unordered_results():
    expected = ExpectedResult(
        columns=["name"],
        rows=[["Engineering"], ["Sales"]],
        ordered=False,
    )
    execution = {
        "columns": ["name"],
        "rows": [["Sales"], ["Engineering"]],
    }

    assert compare_execution(execution, expected).equivalent is True


def test_result_comparison_rejects_different_rows():
    expected = ExpectedResult(columns=["count"], rows=[[12]])
    execution = {"columns": ["count"], "rows": [[11]]}

    result = compare_execution(execution, expected)

    assert result.equivalent is False
    assert result.reason == "row values differ"


def test_offline_report_omits_sql_by_default(monkeypatch):
    case = load_dataset(Path("evaluation/cases.json")).cases[0]
    monkeypatch.setattr(
        "evaluation.run.execute_read_only_query",
        lambda query, **kwargs: {
            "columns": case.expected.columns,
            "rows": case.expected.rows,
        },
    )

    result = _offline_case(case, include_sql=False)

    assert result["equivalent"] is True
    assert "sql" not in result


def test_offline_report_includes_sql_only_when_requested(monkeypatch):
    case = load_dataset(Path("evaluation/cases.json")).cases[0]
    monkeypatch.setattr(
        "evaluation.run.execute_read_only_query",
        lambda query, **kwargs: {
            "columns": case.expected.columns,
            "rows": case.expected.rows,
        },
    )

    result = _offline_case(case, include_sql=True)

    assert result["sql"] == case.expected_sql
