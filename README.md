# DataBridge AI

DataBridge AI is a local, read-only natural-language interface for PostgreSQL. It
turns questions in English or German into SQL, executes the query through a
restricted database role, and presents the verified result as an answer, table,
chart, downloadable CSV, and inspectable SQL.

![DataBridge AI interface](docs/screenshot.jpg)

## Capabilities

- Natural-language database questions in English and German
- Deterministic clarification for ambiguous compensation, period, aggregation,
  and department requests before a model call
- Schema explorer with columns, primary keys, and foreign keys
- Agentic table discovery, schema inspection, and query execution
- Validated business glossary with bilingual aliases, metrics, and lifecycle terms
- Structured results with tables, automatic charts, CSV export, and SQL details
- SQLGlot-based single-statement, read-only query validation
- PostgreSQL query-plan checks for cost, result size, full scans, and Cartesian joins
- Configurable table and column access rules with sensitive-value masking
- Bounded result sets, statement timeouts, and a database role limited to `SELECT`
- Constant-time API token validation and per-token request limiting
- Request IDs, privacy-safe structured events, and authenticated Prometheus metrics
- Correct/incorrect query feedback with local JSONL export
- Forty-case bilingual evaluation with twelve adversarial SQL safety cases
- Docker Compose setup with health checks and an optional pgAdmin profile
- FastAPI OpenAPI documentation at `http://localhost:8000/docs`

## Architecture

```mermaid
flowchart LR
    U["User"] --> UI["Streamlit UI"]
    UI -->|"X-API-Key"| API["FastAPI"]
    API --> CLARIFY["Ambiguity and privacy checks"]
    CLARIFY --> AGENT["LangChain agent"]
    AGENT <--> MODEL["Google Gemini"]
    AGENT --> GLOSSARY["Business glossary"]
    AGENT --> TOOLS["Database tools"]
    TOOLS --> GUARD["SQL and column-policy guards"]
    GUARD --> PLAN["PostgreSQL EXPLAIN guard"]
    PLAN --> ROLE["Read-only PostgreSQL role"]
    ROLE --> DB[("PostgreSQL")]
    DB --> UI
    API --> METRICS["Prometheus metadata"]
    UI --> FEEDBACK[("Local feedback")]
```

The included database contains synthetic departments, employees, and projects so
the full workflow is usable immediately.

## Requirements

- Docker Desktop with Docker Compose
- A Google API key with access to the configured Gemini model

## Quick Start

1. Create the local configuration file:

   ```bash
   cp .env.example .env
   ```

2. Set `GOOGLE_API_KEY` in `.env`. Replace every other `replace_me` value with a
   unique random value. Generate suitable values with:

   ```bash
   openssl rand -hex 32
   ```

3. Build and start the application:

   ```bash
   docker compose up -d --build
   ```

4. Open `http://localhost:8501`.

Check service status or stop the application with:

```bash
docker compose ps
docker compose down
```

Existing database volumes keep their original credentials. After changing a
database password, synchronize the roles with:

```bash
./scripts/sync_db_roles.sh
```

To recreate all included local state from scratch:

```bash
docker compose down --volumes
docker compose up -d --build
```

This deletes both the local PostgreSQL data and locally reviewed feedback.

Version 1.1 expands the included synthetic fixture with project departments,
lifecycle status, and dates. Existing installations must recreate the synthetic
volume once to receive the new columns and evaluation records.

## API

The browser UI is the primary interface. The backend can also be called directly:

```bash
curl --request POST http://localhost:8000/api/v1/query \
  --header "Content-Type: application/json" \
  --header "X-API-Key: $APP_SECRET_TOKEN" \
  --data '{"question":"What is the average annual gross salary by department?","language":"en"}'
```

Responses include the natural-language answer, every executed SQL statement,
structured rows, truncation state, request ID, model duration, tool-call count,
and provider-reported token usage. Ambiguous questions return
`clarification_required` without calling the model. Schema metadata is available
from `GET /api/v1/schema` with the same API key.

Validated business definitions are available from `GET /api/v1/glossary`. The
agent receives only glossary entries matched to the current question and can use
the full glossary through a dedicated read-only tool.

The authenticated API also provides `GET /api/v1/privacy`,
`POST /api/v1/feedback`, `GET /api/v1/feedback/export`, and `GET /metrics`.

## Business Glossary

[`semantic_layer.json`](semantic_layer.json) defines table and column
descriptions, German and English aliases, reusable metrics, and business terms.
The included definitions cover employee headcount, average salary, payroll,
project budgets, and the `planned`, `active`, and `completed` project lifecycle.

The file is validated with Pydantic before use. Invalid or missing glossary data
fails closed and returns a generic configuration error. Set
`SEMANTIC_LAYER_PATH` to load a different validated glossary without changing
application code.

## Ambiguity and Privacy

[`privacy_policy.json`](privacy_policy.json) defines table and column allowlists,
denylists, explicit masks, restricted question terms, and automatic masking.
Pydantic validates the policy and SQLGlot enforces it independently of the model.
Set `PRIVACY_POLICY_PATH` to load another policy.

The default policy allows the three synthetic tables, blocks anticipated secret
fields such as password hashes and social-security numbers, and automatically
masks direct email, phone, identifier, and salary outputs. Aggregate salary
metrics remain visible by default because they do not expose a direct employee
value. Set `masking.allow_aggregates` to `false` for stricter masking.

Ambiguity detection runs before the model. Requests with an unclear compensation
basis, date range, aggregation, or department return a focused clarification
question and consume no model tokens.

## Observability

Every HTTP response includes `X-Request-ID`. The query response also includes
model latency, tool-call count, SQL timing, and input/output token counts when the
provider reports them. Authenticated Prometheus metrics are available with:

```bash
curl --silent http://localhost:8000/metrics \
  --header "X-API-Key: $APP_SECRET_TOKEN"
```

Metrics cover request outcomes and duration, model duration and tokens, tool-call
outcomes, SQL duration, rejection reason codes, and feedback ratings. Metric
labels are bounded and never contain request IDs, prompts, SQL, credentials, tool
arguments, or rows. Structured events contain only request ID and numeric or
enumerated metadata. Keep `AGENT_VERBOSE=false`; framework debug output is not a
privacy-safe telemetry channel.

This follows the OpenTelemetry GenAI guidance to collect model, token, duration,
and tool metadata while leaving content capture disabled by default. See
[OpenTelemetry GenAI observability](https://opentelemetry.io/blog/2026/genai-observability/).

## Query Feedback

Answered queries provide **Correct** and **Incorrect** controls. A rating stores
exactly the question, final accepted SQL, and feedback value in a local SQLite
file with mode `0600`. Answers, database rows, credentials, prompts without a
rating, and telemetry are not persisted in the feedback database.

The backend stores feedback in the `feedback_data` Docker volume. Export reviewed
examples from the sidebar or `GET /api/v1/feedback/export`; the JSONL export is
suitable for review and later evaluation-dataset curation. `FEEDBACK_DB_PATH`
changes the local storage path.

## Evaluation

The versioned evaluation dataset contains 40 representative German and English
questions plus 12 unsafe SQL cases. Offline mode executes verified canonical SQL
against PostgreSQL, checks result equivalence, records latency, and confirms that
unsafe statements are rejected. It never calls Gemini:

```bash
docker compose exec backend python -m evaluation.run
```

The verified `company_data_v2` baseline is:

| Metric | Result |
| --- | ---: |
| Canonical execution success | 40/40 (100%) |
| Canonical result equivalence | 40/40 (100%) |
| Unsafe-query rejection | 12/12 (100%) |
| Median / p95 local query latency | 1 ms / 2 ms |

This deterministic baseline validates the dataset and execution controls; it is
not presented as model accuracy. Live Text-to-SQL evaluation is explicitly
opt-in and calls the configured Gemini model once or more per selected case:

```bash
docker compose exec backend python -m evaluation.run --live --limit 5
```

Use `--case CASE_ID` to select specific cases and `--minimum-equivalence` to set
a failure threshold. Save and copy a report from the non-root backend container
with:

```bash
docker compose exec backend python -m evaluation.run --output /tmp/evaluation-report.json
docker compose cp backend:/tmp/evaluation-report.json ./evaluation-report.json
```

Reports omit questions, model answers, database rows, and generated SQL by
default. SQL can be included only with the explicit `--include-sql` option. The
dataset design follows the execution-based evaluation direction represented by
[Spider 2.0](https://arxiv.org/abs/2411.07763).

## Query-Plan Guard

Every accepted PostgreSQL query is inspected with `EXPLAIN (FORMAT JSON)` before
execution. The application rejects plans that exceed configured total-cost or
result-row limits, large sequential scans, and large unconditioned nested loops.
It does not use `EXPLAIN ANALYZE`, so plan inspection does not execute the query.

| Environment variable | Default |
| --- | ---: |
| `QUERY_PLAN_GUARD_ENABLED` | `true` |
| `MAX_QUERY_PLAN_COST` | `10000` |
| `MAX_QUERY_PLAN_ROWS` | `10000` |
| `MAX_SEQUENTIAL_SCAN_ROWS` | `50000` |
| `MAX_CARTESIAN_JOIN_ROWS` | `10000` |

Planner estimates depend on database statistics and workload. Tune these limits
for the target database rather than disabling the guard. See the
[PostgreSQL EXPLAIN documentation](https://www.postgresql.org/docs/current/using-explain.html)
for plan and cost semantics.

## Development

Create a virtual environment and install the pinned development dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
```

Run all local checks:

```bash
ruff check .
ruff format --check .
python -m compileall -q agent.py app.py config.py csv_export.py database.py \
  ambiguity.py feedback.py main.py observability.py privacy_policy.py query_log.py \
  query_plan.py rate_limit.py result_formatting.py schema_service.py \
  semantic_layer.py sql_safety.py sql_tools.py evaluation tests
pytest -q
docker compose config --quiet
```

Tests use isolated SQLite databases and mocked agents, so they do not call Gemini
or require PostgreSQL.

## Security Model

DataBridge AI uses several independent controls:

1. The backend accepts one authenticated request token and compares it in constant
   time.
2. SQL is parsed as PostgreSQL and must contain exactly one read-only query.
3. Questions and generated SQL must pass independent table and column policy
   checks; direct sensitive outputs are masked before reaching the model or UI.
4. Accepted SQL must pass configurable PostgreSQL query-plan limits before it can
   execute.
5. The agent database role has `SELECT` privileges, read-only transactions, and
   short server-side timeouts.
6. Query output is capped before it is returned to the agent or UI.
7. Database and plan errors are converted to generic messages before they reach
   the model or browser.
8. Metrics and structured events omit prompts, SQL, credentials, and returned
   rows by default.
9. Services bind to `127.0.0.1` by default, and containers run as non-root users
   where applicable.

Questions, allowed schema metadata, generated SQL, and policy-filtered rows are
sent to the configured model provider while answering a request. Review
data-handling requirements before connecting confidential data. The feedback
database deliberately stores reviewed questions and SQL locally; protect and
delete that volume according to the data's sensitivity.

The API token is service-to-service protection for local use, not a multi-user
identity system. Do not expose this stack directly to the internet. Add TLS,
user authentication, durable distributed rate limiting, audit controls, and a
managed secrets solution before any networked deployment.

See [SECURITY.md](SECURITY.md) for reporting guidance and additional safeguards.

## Optional pgAdmin

Set `PGADMIN_DEFAULT_PASSWORD` to a unique value, then start the profile:

```bash
docker compose --profile admin up -d pgadmin
```

Open `http://localhost:5050`. PostgreSQL is reachable from pgAdmin at host
`postgres`, port `5432`.

## License

Licensed under the [MIT License](LICENSE).
