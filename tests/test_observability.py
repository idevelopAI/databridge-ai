import json
import logging
from types import SimpleNamespace
from uuid import uuid4

from prometheus_client import generate_latest

from observability import (
    CURRENT_REQUEST_ID,
    ObservabilityCallbackHandler,
    log_query_event,
)


def test_callback_records_metadata_without_prompt_or_tool_content():
    handler = ObservabilityCallbackHandler()
    model_run = uuid4()
    tool_run = uuid4()
    handler.on_chat_model_start(
        {},
        [[SimpleNamespace(content="PRIVATE PROMPT")]],
        run_id=model_run,
    )
    response = SimpleNamespace(
        generations=[
            [
                SimpleNamespace(
                    message=SimpleNamespace(
                        usage_metadata={"input_tokens": 12, "output_tokens": 4}
                    )
                )
            ]
        ]
    )
    handler.on_llm_end(response, run_id=model_run)
    handler.on_tool_start(
        {"name": "sql_db_query"},
        "SELECT private_data FROM employees",
        run_id=tool_run,
    )
    handler.on_tool_end({"rows": [["private"]]}, run_id=tool_run)

    telemetry = handler.snapshot()
    metrics = generate_latest().decode("utf-8")

    assert telemetry.tool_call_count == 1
    assert telemetry.input_tokens == 12
    assert telemetry.output_tokens == 4
    assert "databridge_model_duration_seconds" in metrics
    assert "databridge_tool_calls_total" in metrics
    assert "databridge_tool_duration_seconds" in metrics
    assert "PRIVATE PROMPT" not in metrics
    assert "private_data" not in metrics


def test_structured_event_contains_only_safe_metadata(caplog):
    request_token = CURRENT_REQUEST_ID.set("request-123")
    try:
        with caplog.at_level("INFO", logger="uvicorn.error.databridge.telemetry"):
            log_query_event(
                event="query_completed",
                outcome="answered",
                duration_ms=25,
                sql_duration_ms=3,
            )
    finally:
        CURRENT_REQUEST_ID.reset(request_token)

    payload = json.loads(caplog.records[-1].message)
    assert payload == {
        "duration_ms": 25,
        "event": "query_completed",
        "outcome": "answered",
        "request_id": "request-123",
        "sql_duration_ms": 3,
    }


def test_structured_event_logger_emits_info_in_production():
    logger = logging.getLogger("uvicorn.error.databridge.telemetry")

    assert logger.isEnabledFor(logging.INFO)
