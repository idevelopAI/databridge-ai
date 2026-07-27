import argparse
import json
import os
import statistics
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv

from evaluation.comparison import compare_execution
from evaluation.models import EvaluationCase, load_dataset
from query_log import CURRENT_SQL_EXECUTIONS
from sql_tools import execute_read_only_query


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def _offline_case(
    case: EvaluationCase,
    *,
    include_sql: bool,
) -> dict[str, Any]:
    started_at = perf_counter()
    execution = execute_read_only_query(case.expected_sql, mask_results=False)
    duration_ms = round((perf_counter() - started_at) * 1000)
    if "error" in execution:
        return {
            "id": case.id,
            "executed": False,
            "equivalent": False,
            "duration_ms": duration_ms,
            "reason": "canonical query was rejected",
        }
    comparison = compare_execution(execution, case.expected, require_column_names=True)
    result = {
        "id": case.id,
        "executed": True,
        "equivalent": comparison.equivalent,
        "duration_ms": duration_ms,
        "reason": comparison.reason,
    }
    if include_sql:
        result["sql"] = case.expected_sql
    return result


def _live_case(
    case: EvaluationCase,
    agent,
    *,
    include_sql: bool,
) -> dict[str, Any]:
    from main import QueryRequest, build_agent_prompt

    executions: list[dict[str, Any]] = []
    token = CURRENT_SQL_EXECUTIONS.set(executions)
    started_at = perf_counter()
    try:
        response = agent.invoke(
            {
                "input": build_agent_prompt(
                    QueryRequest(question=case.question, language=case.language)
                )
            }
        )
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000)
        return {
            "id": case.id,
            "executed": False,
            "equivalent": False,
            "duration_ms": duration_ms,
            "reason": "live evaluation request failed",
            "input_tokens": 0,
            "output_tokens": 0,
        }
    finally:
        CURRENT_SQL_EXECUTIONS.reset(token)

    duration_ms = round((perf_counter() - started_at) * 1000)
    if not executions:
        return {
            "id": case.id,
            "executed": False,
            "equivalent": False,
            "duration_ms": duration_ms,
            "reason": "the agent executed no accepted query",
            "input_tokens": 0,
            "output_tokens": 0,
        }

    telemetry = response.get("telemetry")
    if hasattr(telemetry, "input_tokens"):
        input_tokens = int(telemetry.input_tokens)
        output_tokens = int(telemetry.output_tokens)
    elif isinstance(telemetry, dict):
        input_tokens = int(telemetry.get("input_tokens", 0))
        output_tokens = int(telemetry.get("output_tokens", 0))
    else:
        input_tokens = 0
        output_tokens = 0

    execution = executions[-1]
    comparison = compare_execution(execution, case.expected)
    result = {
        "id": case.id,
        "executed": True,
        "equivalent": comparison.equivalent,
        "duration_ms": duration_ms,
        "reason": comparison.reason,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if include_sql:
        result["sql"] = execution.get("sql", "")
    return result


def _safety_results(dataset) -> list[dict[str, Any]]:
    results = []
    for case in dataset.unsafe_cases:
        output = execute_read_only_query(case.sql)
        results.append({"id": case.id, "rejected": "error" in output})
    return results


def _report(
    mode: str,
    fixture: str,
    cases,
    safety_results,
    *,
    input_price_per_million_usd: float,
    output_price_per_million_usd: float,
) -> dict[str, Any]:
    durations = [case["duration_ms"] for case in cases]
    executed = sum(case["executed"] for case in cases)
    equivalent = sum(case["equivalent"] for case in cases)
    rejected = sum(case["rejected"] for case in safety_results)
    total_cases = len(cases)
    total_unsafe = len(safety_results)
    input_tokens = sum(case.get("input_tokens", 0) for case in cases)
    output_tokens = sum(case.get("output_tokens", 0) for case in cases)
    total_cost_usd = (
        input_tokens * input_price_per_million_usd
        + output_tokens * output_price_per_million_usd
    ) / 1_000_000
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "fixture": fixture,
        "summary": {
            "cases": total_cases,
            "execution_success_rate": executed / total_cases if total_cases else 0,
            "result_equivalence_rate": equivalent / total_cases if total_cases else 0,
            "unsafe_cases": total_unsafe,
            "unsafe_rejection_rate": rejected / total_unsafe if total_unsafe else 0,
            "median_latency_ms": (
                round(statistics.median(durations)) if durations else 0
            ),
            "p50_latency_ms": (round(statistics.median(durations)) if durations else 0),
            "p95_latency_ms": _percentile(durations, 0.95),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost_usd": round(total_cost_usd, 6),
            "cost_per_query_usd": (
                round(total_cost_usd / total_cases, 6) if total_cases else 0
            ),
        },
        "cases": cases,
        "unsafe_cases": safety_results,
    }


def _print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Mode: {report['mode']}")
    print(f"Fixture: {report['fixture']}")
    print(
        "Execution success: "
        f"{summary['execution_success_rate']:.1%} ({summary['cases']} cases)"
    )
    print(f"Result equivalence: {summary['result_equivalence_rate']:.1%}")
    print(
        "Unsafe query rejection: "
        f"{summary['unsafe_rejection_rate']:.1%} "
        f"({summary['unsafe_cases']} cases)"
    )
    print(
        f"Latency: p50 {summary['p50_latency_ms']} ms, "
        f"p95 {summary['p95_latency_ms']} ms"
    )
    print(f"Tokens: {summary['input_tokens']} input, {summary['output_tokens']} output")
    print(f"Estimated cost/query: ${summary['cost_per_query_usd']:.6f}")
    for case in report["cases"]:
        status = "PASS" if case["equivalent"] else "FAIL"
        print(f"{status} {case['id']} {case['duration_ms']} ms")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate DataBridge AI Text-to-SQL")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).with_name("cases.json"),
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--live", action="store_true")
    mode_group.add_argument("--recorded", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--include-sql", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-equivalence", type=float)
    parser.add_argument(
        "--input-price-per-million-usd",
        type=float,
        default=float(os.environ.get("EVAL_INPUT_PRICE_PER_MILLION_USD", "0.30")),
    )
    parser.add_argument(
        "--output-price-per-million-usd",
        type=float,
        default=float(os.environ.get("EVAL_OUTPUT_PRICE_PER_MILLION_USD", "2.50")),
    )
    parser.add_argument("--max-cost-usd", type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be greater than zero")
    if args.minimum_equivalence is not None and not (
        0 <= args.minimum_equivalence <= 1
    ):
        raise SystemExit("--minimum-equivalence must be between zero and one")
    if args.input_price_per_million_usd < 0:
        raise SystemExit("--input-price-per-million-usd cannot be negative")
    if args.output_price_per_million_usd < 0:
        raise SystemExit("--output-price-per-million-usd cannot be negative")
    if args.max_cost_usd is not None and args.max_cost_usd <= 0:
        raise SystemExit("--max-cost-usd must be greater than zero")

    load_dotenv()
    dataset = load_dataset(args.dataset)
    cases = dataset.cases
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.id in selected]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No evaluation cases selected")

    mode = "offline"
    agent_context = nullcontext(None)
    if args.live:
        from agent import get_agent_executor

        mode = "live"
        print(
            f"Live mode: the configured model provider will receive {len(cases)} cases."
        )
        agent_context = nullcontext(get_agent_executor())
    elif args.recorded:
        from recorded_demo import build_recorded_demo_agent

        mode = "recorded"
        print("Recorded mode: no model provider is called.")
        agent_context = nullcontext(build_recorded_demo_agent(mask_results=False))

    with agent_context as agent:
        case_results = []
        for case in cases:
            result = (
                _live_case(case, agent, include_sql=args.include_sql)
                if mode in {"live", "recorded"}
                else _offline_case(case, include_sql=args.include_sql)
            )
            case_results.append(result)
            if args.max_cost_usd is not None:
                current_cost = (
                    sum(item.get("input_tokens", 0) for item in case_results)
                    * args.input_price_per_million_usd
                    + sum(item.get("output_tokens", 0) for item in case_results)
                    * args.output_price_per_million_usd
                ) / 1_000_000
                if current_cost >= args.max_cost_usd:
                    print(
                        f"Cost cap reached after {len(case_results)} cases; "
                        "remaining cases were skipped."
                    )
                    break

    report = _report(
        mode,
        dataset.fixture,
        case_results,
        _safety_results(dataset),
        input_price_per_million_usd=args.input_price_per_million_usd,
        output_price_per_million_usd=args.output_price_per_million_usd,
    )
    _print_report(report)
    if args.output:
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    minimum = args.minimum_equivalence
    if minimum is None:
        minimum = 0 if args.live else 1
    summary = report["summary"]
    return int(
        summary["result_equivalence_rate"] < minimum
        or summary["unsafe_rejection_rate"] < 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
