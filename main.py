import json
import logging
import secrets
from time import perf_counter
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field

from agent import get_agent_executor
from config import get_app_secret_token
from query_log import CURRENT_SQL_EXECUTIONS
from rate_limit import enforce_rate_limit
from result_formatting import ensure_answer_includes_result
from schema_service import clear_schema_cache, get_schema_metadata
from semantic_layer import get_semantic_layer_data, semantic_context_for_question

logger = logging.getLogger("databridge")

app = FastAPI(
    title="DataBridge AI",
    description="A read-only natural-language interface for PostgreSQL.",
    version="1.1.0",
)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


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
    answer: str
    executions: list[QueryExecution] = Field(default_factory=list)
    duration_ms: int = 0


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
        logger.exception("Agent readiness check failed")
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
        logger.exception("Schema configuration failed")
        raise HTTPException(
            status_code=503, detail="Database is not configured."
        ) from None
    except Exception:
        logger.exception("Schema inspection failed")
        raise HTTPException(
            status_code=500, detail="Failed to inspect database schema."
        ) from None


@app.get("/api/v1/glossary", response_model=dict)
def glossary(api_key: str = Depends(verify_api_key)) -> dict:
    del api_key
    try:
        return get_semantic_layer_data()
    except RuntimeError:
        logger.exception("Business glossary configuration failed")
        raise HTTPException(
            status_code=503, detail="Business glossary is not configured."
        ) from None


@app.post("/api/v1/query", response_model=QueryResponse)
def ask_database(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key),
) -> QueryResponse:
    enforce_rate_limit(api_key)
    started_at = perf_counter()
    executions: list[dict[str, Any]] = []
    execution_log_token = CURRENT_SQL_EXECUTIONS.set(executions)

    try:
        response = get_agent_executor().invoke({"input": build_agent_prompt(request)})
        raw_output = response.get("output", "")
        clean_answer = ensure_answer_includes_result(
            str(raw_output),
            executions,
            language=request.language,
        )
        return QueryResponse(
            answer=clean_answer,
            executions=executions,
            duration_ms=round((perf_counter() - started_at) * 1000),
        )
    except RuntimeError:
        logger.exception("Agent configuration failed")
        raise HTTPException(
            status_code=503, detail="Agent is not configured."
        ) from None
    except Exception:
        logger.exception("Database agent request failed")
        raise HTTPException(
            status_code=500,
            detail="The database agent failed to answer the question.",
        ) from None
    finally:
        CURRENT_SQL_EXECUTIONS.reset(execution_log_token)
