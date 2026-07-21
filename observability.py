import json
import logging
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from prometheus_client import Counter, Histogram

logger = logging.getLogger("uvicorn.error.databridge.telemetry")
logger.setLevel(logging.INFO)

CURRENT_REQUEST_ID: ContextVar[str] = ContextVar("CURRENT_REQUEST_ID", default="")

REQUESTS_TOTAL = Counter(
    "databridge_requests_total",
    "DataBridge query requests by outcome.",
    ["outcome"],
)
REQUEST_DURATION = Histogram(
    "databridge_request_duration_seconds",
    "End-to-end DataBridge query request duration.",
)
MODEL_DURATION = Histogram(
    "databridge_model_duration_seconds",
    "Model call duration without prompt or response content.",
)
MODEL_TOKENS = Counter(
    "databridge_model_tokens_total",
    "Model tokens reported by the provider.",
    ["type"],
)
TOOL_CALLS = Counter(
    "databridge_tool_calls_total",
    "Agent tool calls by bounded tool name and outcome.",
    ["tool", "outcome"],
)
TOOL_DURATION = Histogram(
    "databridge_tool_duration_seconds",
    "Agent tool duration without arguments or results.",
    ["tool"],
)
SQL_DURATION = Histogram(
    "databridge_sql_duration_seconds",
    "Accepted SQL execution duration.",
)
REJECTIONS = Counter(
    "databridge_rejections_total",
    "Rejected requests and queries by bounded stage and reason.",
    ["stage", "reason"],
)
FEEDBACK = Counter(
    "databridge_feedback_total",
    "Locally stored query feedback by rating.",
    ["rating"],
)

KNOWN_TOOLS = {
    "sql_db_business_glossary",
    "sql_db_list_tables",
    "sql_db_query",
    "sql_db_schema",
}
KNOWN_REJECTION_STAGES = {
    "agent",
    "ambiguity",
    "privacy",
    "query_plan",
    "rate_limit",
    "sql_safety",
}
KNOWN_REJECTION_REASONS = {
    "agent_error",
    "aggregation",
    "compensation_basis",
    "configuration",
    "database_error",
    "date_range",
    "department",
    "non_row_result",
    "plan_cartesian_join",
    "plan_cost",
    "plan_full_scan",
    "plan_rows",
    "plan_uninspectable",
    "rate_limit",
    "restricted_column",
    "restricted_field",
    "restricted_table",
    "sql_parse",
    "sql_prohibited",
    "uninspectable_sql",
    "wildcard_selection",
}


@dataclass(frozen=True)
class AgentTelemetry:
    model_duration_ms: int = 0
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ObservabilityCallbackHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        super().__init__()
        self._model_starts: dict[UUID, float] = {}
        self._tool_starts: dict[UUID, tuple[str, float]] = {}
        self._model_duration_seconds = 0.0
        self._tool_call_count = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def _model_start(self, run_id: UUID) -> None:
        self._model_starts[run_id] = perf_counter()

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del serialized, prompts, kwargs
        self._model_start(run_id)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del serialized, messages, kwargs
        self._model_start(run_id)

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        del kwargs
        started_at = self._model_starts.pop(run_id, None)
        if started_at is not None:
            duration = perf_counter() - started_at
            self._model_duration_seconds += duration
            MODEL_DURATION.observe(duration)

        input_tokens = 0
        output_tokens = 0
        for generations in getattr(response, "generations", []):
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
                input_tokens += int(usage.get("input_tokens", 0) or 0)
                output_tokens += int(usage.get("output_tokens", 0) or 0)
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        if input_tokens:
            MODEL_TOKENS.labels(type="input").inc(input_tokens)
        if output_tokens:
            MODEL_TOKENS.labels(type="output").inc(output_tokens)

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        del error, kwargs
        started_at = self._model_starts.pop(run_id, None)
        if started_at is not None:
            duration = perf_counter() - started_at
            self._model_duration_seconds += duration
            MODEL_DURATION.observe(duration)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del input_str, kwargs
        raw_name = str(serialized.get("name", ""))
        tool_name = raw_name if raw_name in KNOWN_TOOLS else "other"
        self._tool_starts[run_id] = (tool_name, perf_counter())
        self._tool_call_count += 1

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        del output, kwargs
        tool_name, started_at = self._tool_starts.pop(run_id, ("other", 0.0))
        TOOL_CALLS.labels(tool=tool_name, outcome="success").inc()
        if started_at:
            TOOL_DURATION.labels(tool=tool_name).observe(perf_counter() - started_at)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del error, kwargs
        tool_name, started_at = self._tool_starts.pop(run_id, ("other", 0.0))
        TOOL_CALLS.labels(tool=tool_name, outcome="error").inc()
        if started_at:
            TOOL_DURATION.labels(tool=tool_name).observe(perf_counter() - started_at)

    def snapshot(self) -> AgentTelemetry:
        return AgentTelemetry(
            model_duration_ms=round(self._model_duration_seconds * 1000),
            tool_call_count=self._tool_call_count,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
        )


def get_request_id() -> str:
    return CURRENT_REQUEST_ID.get()


def record_request(outcome: str, duration_seconds: float) -> None:
    safe_outcome = (
        outcome
        if outcome in {"answered", "clarification", "rejected", "error"}
        else "error"
    )
    REQUESTS_TOTAL.labels(outcome=safe_outcome).inc()
    REQUEST_DURATION.observe(max(duration_seconds, 0))


def record_sql_duration(duration_seconds: float) -> None:
    SQL_DURATION.observe(max(duration_seconds, 0))


def record_rejection(stage: str, reason: str) -> None:
    safe_stage = stage if stage in KNOWN_REJECTION_STAGES else "agent"
    safe_reason = reason if reason in KNOWN_REJECTION_REASONS else "agent_error"
    REJECTIONS.labels(stage=safe_stage, reason=safe_reason).inc()


def record_feedback(rating: str) -> None:
    safe_rating = rating if rating in {"correct", "incorrect"} else "incorrect"
    FEEDBACK.labels(rating=safe_rating).inc()


def log_query_event(
    *,
    event: str,
    outcome: str,
    duration_ms: int,
    telemetry: AgentTelemetry | None = None,
    sql_duration_ms: int = 0,
    rejection_reason: str = "",
) -> None:
    payload: dict[str, Any] = {
        "event": event,
        "request_id": get_request_id(),
        "outcome": outcome,
        "duration_ms": duration_ms,
        "sql_duration_ms": sql_duration_ms,
    }
    if telemetry is not None:
        payload.update(asdict(telemetry))
    if rejection_reason:
        payload["rejection_reason"] = (
            rejection_reason
            if rejection_reason in KNOWN_REJECTION_REASONS
            else "agent_error"
        )
    logger.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))
