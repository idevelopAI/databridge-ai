from query_plan import QueryPlanLimits, evaluate_query_plan

LIMITS = QueryPlanLimits(
    max_total_cost=1000,
    max_result_rows=5000,
    max_sequential_scan_rows=5000,
    max_cartesian_join_rows=2000,
)


def plan_payload(**overrides):
    plan = {
        "Node Type": "Index Scan",
        "Total Cost": 20,
        "Plan Rows": 10,
    }
    plan.update(overrides)
    return [{"Plan": plan}]


def test_accepts_bounded_query_plan():
    assert evaluate_query_plan(plan_payload(), LIMITS).is_safe is True


def test_rejects_high_total_cost():
    result = evaluate_query_plan(plan_payload(**{"Total Cost": 1001}), LIMITS)

    assert result.is_safe is False
    assert result.reason == "the estimated query cost is too high"


def test_rejects_large_estimated_result():
    result = evaluate_query_plan(plan_payload(**{"Plan Rows": 5001}), LIMITS)

    assert result.is_safe is False
    assert result.reason == "the estimated result is too large"


def test_rejects_large_sequential_scan_in_child_plan():
    result = evaluate_query_plan(
        plan_payload(
            Plans=[
                {
                    "Node Type": "Seq Scan",
                    "Plan Rows": 5001,
                    "Total Cost": 500,
                }
            ]
        ),
        LIMITS,
    )

    assert result.is_safe is False
    assert result.reason == "the query requires a large full-table scan"


def test_rejects_large_cartesian_nested_loop():
    result = evaluate_query_plan(
        plan_payload(
            **{
                "Node Type": "Nested Loop",
                "Plan Rows": 3000,
                "Plans": [
                    {"Node Type": "Seq Scan", "Plan Rows": 100},
                    {"Node Type": "Seq Scan", "Plan Rows": 30},
                ],
            }
        ),
        LIMITS,
    )

    assert result.is_safe is False
    assert result.reason == "the query creates a large Cartesian join"


def test_allows_conditioned_nested_loop():
    result = evaluate_query_plan(
        plan_payload(
            **{
                "Node Type": "Nested Loop",
                "Plan Rows": 3000,
                "Join Filter": "(a.id = b.a_id)",
                "Plans": [
                    {"Node Type": "Index Scan", "Plan Rows": 100},
                    {"Node Type": "Index Scan", "Plan Rows": 30},
                ],
            }
        ),
        LIMITS,
    )

    assert result.is_safe is True


def test_rejects_malformed_plan_without_exposing_details():
    result = evaluate_query_plan({"unexpected": "value"}, LIMITS)

    assert result.is_safe is False
    assert result.reason == "the query plan could not be inspected"
