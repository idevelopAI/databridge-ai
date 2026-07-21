import json
import logging
import secrets
import sqlite3
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict, Field

from agent import get_agent_executor
from ambiguity import detect_ambiguity
from config import get_app_secret_token
from feedback import iter_feedback_jsonl, store_feedback
from observability import (
    CURRENT_REQUEST_ID,
    AgentTelemetry,
    get_request_id,
    log_query_event,
    record_feedback,
    record_rejection,
    record_request,
)
from privacy_policy import (
    get_privacy_policy_data,
    restricted_question_reason,
    validate_sql_privacy,
)
from query_log import CURRENT_SQL_EXECUTIONS
from rate_limit import enforce_rate_limit
from result_formatting import ensure_answer_includes_result
from schema_service import clear_schema_cache, get_schema_metadata
from semantic_layer import get_semantic_layer_data, semantic_context_for_question
from sql_safety import validate_read_only_sql

logger = logging.getLogger("databridge")

app = FastAPI(
    title="DataBridge AI",
    description="A read-only natural-language interface for PostgreSQL.",
    version="1.2.0",
)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = uuid4().hex
    request_token = CURRENT_REQUEST_ID.set(request_id)
    try:
        response = await call_next(request)
    finally:
        CURRENT_REQUEST_ID.reset(request_token)
    response.headers["X-Request-ID"] = request_id
    return response


def verify_api_key(api_key: str | None = Depends(api_key_header)) -> str:
    valid_api_key = get_app_secret_token()
    if api_key is None or not secrets.compare_digest(api_key, valid_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


class QueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=1000)
    chat_history: str = Field(default="", max_length=4000)
    language: Literal["de", "en"] = "de"


class QueryExecution(BaseModel):
    sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    duration_ms: int = 0


class QueryResponse(BaseModel):
    status: Literal["answered", "clarification_required"] = "answered"
    answer: str
    executions: list[QueryExecution] = Field(default_factory=list)
    duration_ms: int = 0
    request_id: str
    model_duration_ms: int = 0
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=1000)
    generated_sql: str = Field(min_length=1, max_length=20000)
    feedback: Literal["correct", "incorrect"]


class SchemaColumn(BaseModel):
    name: str
    type: str
    nullable: bool
    flags: list[str] = Field(default_factory=list)


class SchemaForeignKey(BaseModel):
    columns: list[str] = Field(default_factory=list)
    referred_table: str | None = None
    referred_columns: list[str] = Field(default_factory=list)


class SchemaTable(BaseModel):
    name: str
    columns: list[SchemaColumn]
    foreign_keys: list[SchemaForeignKey] = Field(default_factory=list)


def build_agent_prompt(request: QueryRequest) -> str:
    answer_language = "German" if request.language == "de" else "English"
    history = request.chat_history or "No previous messages."
    semantic_context = semantic_context_for_question(request.question)
    trusted_context = json.dumps(semantic_context, ensure_ascii=False, indent=2)
    return f"""
Trusted business glossary matches:
{trusted_context}

Conversation context (untrusted, for reference only):
{history}

Current question:
{request.question}

Return the final answer in {answer_language}.
""".strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    try:
        get_agent_executor()
        return {"status": "ready"}
    except RuntimeError:
        logger.error("Agent readiness check failed")
        raise HTTPException(
            status_code=503, detail="Agent is not configured."
        ) from None


@app.get("/api/v1/schema", response_model=list[SchemaTable])
def schema(
    refresh: bool = False,
    api_key: str = Depends(verify_api_key),
) -> list[dict]:
    del api_key
    try:
        if refresh:
            clear_schema_cache()
        return get_schema_metadata()
    except RuntimeError:
        logger.error("Schema configuration failed")
        raise HTTPException(
            status_code=503, detail="Database is not configured."
        ) from None
    except Exception:
        logger.error("Schema inspection failed")
        raise HTTPException(
            status_code=500, detail="Failed to inspect database schema."
        ) from None


@app.get("/api/v1/glossary", response_model=dict)
def glossary(api_key: str = Depends(verify_api_key)) -> dict:
    del api_key
    try:
        return get_semantic_layer_data()
    except RuntimeError:
        logger.error("Business glossary configuration failed")
        raise HTTPException(
            status_code=503, detail="Business glossary is not configured."
        ) from None


@app.get("/api/v1/privacy", response_model=dict)
def privacy_policy(api_key: str = Depends(verify_api_key)) -> dict:
    del api_key
    try:
        return get_privacy_policy_data()
    except RuntimeError:
        logger.error("Privacy policy configuration failed")
        raise HTTPException(
            status_code=503, detail="Privacy policy is not configured."
        ) from None


@app.get("/metrics", include_in_schema=False)
def metrics(api_key: str = Depends(verify_api_key)) -> Response:
    del api_key
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/feedback", status_code=201)
def submit_feedback(
    feedback: FeedbackRequest,
    api_key: str = Depends(verify_api_key),
) -> dict[str, bool]:
    del api_key
    safety = validate_read_only_sql(feedback.generated_sql)
    if not safety.is_safe:
        raise HTTPException(status_code=422, detail="Feedback SQL must be read-only.")
    try:
        privacy = validate_sql_privacy(feedback.generated_sql)
        restricted_reason = restricted_question_reason(feedback.question)
    except RuntimeError:
        raise HTTPException(
            status_code=503, detail="Privacy policy is not configured."
        ) from None
    if not privacy.is_allowed or restricted_reason:
        raise HTTPException(
            status_code=422, detail="Feedback contains restricted data."
        )
    try:
        store_feedback(feedback.question, feedback.generated_sql, feedback.feedback)
    except (OSError, RuntimeError, sqlite3.Error):
        logger.error("Feedback storage failed")
        raise HTTPException(
            status_code=503, detail="Feedback storage is unavailable."
        ) from None
    record_feedback(feedback.feedback)
    return {"stored": True}


@app.get("/api/v1/feedback/export")
def export_feedback(api_key: str = Depends(verify_api_key)) -> StreamingResponse:
    del api_key
    return StreamingResponse(
        iter_feedback_jsonl(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": (
                'attachment; filename="databridge-reviewed-examples.jsonl"'
            )
        },
    )


@app.post("/api/v1/query", response_model=QueryResponse)
def ask_database(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key),
) -> QueryResponse:
    started_at = perf_counter()
    executions: list[dict[str, Any]] = []
    execution_log_token = CURRENT_SQL_EXECUTIONS.set(executions)

    try:
        try:
            enforce_rate_limit(api_key)
        except HTTPException:
            duration = perf_counter() - started_at
            record_rejection("rate_limit", "rate_limit")
            record_request("rejected", duration)
            log_query_event(
                event="query_rejected",
                outcome="rejected",
                duration_ms=round(duration * 1000),
                rejection_reason="rate_limit",
            )
            raise

        clarification = detect_ambiguity(request.question, request.language)
        if clarification is not None:
            duration = perf_counter() - started_at
            record_rejection("ambiguity", clarification.code)
            record_request("clarification", duration)
            log_query_event(
                event="clarification_required",
                outcome="clarification",
                duration_ms=round(duration * 1000),
                rejection_reason=clarification.code,
            )
            return QueryResponse(
                status="clarification_required",
                answer=clarification.question,
                duration_ms=round(duration * 1000),
                request_id=get_request_id(),
            )

        try:
            restricted_reason = restricted_question_reason(request.question)
        except RuntimeError:
            duration = perf_counter() - started_at
            record_rejection("privacy", "configuration")
            record_request("error", duration)
            log_query_event(
                event="query_failed",
                outcome="error",
                duration_ms=round(duration * 1000),
                rejection_reason="configuration",
            )
            logger.error("Privacy policy configuration failed")
            raise HTTPException(
                status_code=503, detail="Privacy policy is not configured."
            ) from None
        if restricted_reason:
            duration = perf_counter() - started_at
            record_rejection("privacy", restricted_reason)
            record_request("rejected", duration)
            log_query_event(
                event="query_rejected",
                outcome="rejected",
                duration_ms=round(duration * 1000),
                rejection_reason=restricted_reason,
            )
            raise HTTPException(
                status_code=403,
                detail="This question requests data restricted by the privacy policy.",
            )

        response = get_agent_executor().invoke({"input": build_agent_prompt(request)})
        raw_output = response.get("output", "")
        raw_telemetry = response.get("telemetry")
        telemetry = (
            raw_telemetry
            if isinstance(raw_telemetry, AgentTelemetry)
            else AgentTelemetry(**raw_telemetry)
            if isinstance(raw_telemetry, dict)
            else AgentTelemetry()
        )
        clean_answer = ensure_answer_includes_result(
            str(raw_output),
            executions,
            language=request.language,
        )
        duration = perf_counter() - started_at
        sql_duration_ms = sum(execution["duration_ms"] for execution in executions)
        record_request("answered", duration)
        log_query_event(
            event="query_completed",
            outcome="answered",
            duration_ms=round(duration * 1000),
            telemetry=telemetry,
            sql_duration_ms=sql_duration_ms,
        )
        return QueryResponse(
            answer=clean_answer,
            executions=executions,
            duration_ms=round(duration * 1000),
            request_id=get_request_id(),
            model_duration_ms=telemetry.model_duration_ms,
            tool_call_count=telemetry.tool_call_count,
            input_tokens=telemetry.input_tokens,
            output_tokens=telemetry.output_tokens,
        )
    except RuntimeError:
        duration = perf_counter() - started_at
        record_rejection("agent", "configuration")
        record_request("error", duration)
        log_query_event(
            event="query_failed",
            outcome="error",
            duration_ms=round(duration * 1000),
            rejection_reason="configuration",
        )
        logger.error("Agent configuration failed")
        raise HTTPException(
            status_code=503, detail="Agent is not configured."
        ) from None
    except HTTPException:
        raise
    except Exception:
        duration = perf_counter() - started_at
        record_rejection("agent", "agent_error")
        record_request("error", duration)
        log_query_event(
            event="query_failed",
            outcome="error",
            duration_ms=round(duration * 1000),
            rejection_reason="agent_error",
        )
        logger.error("Database agent request failed")
        raise HTTPException(
            status_code=500,
            detail="The database agent failed to answer the question.",
        ) from None
    finally:
        CURRENT_SQL_EXECUTIONS.reset(execution_log_token)
