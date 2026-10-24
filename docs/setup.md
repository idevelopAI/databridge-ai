# Setup and Configuration

[Back to the README](../README.md)

## Requirements

- Docker Desktop with Docker Compose
- A Google API key with access to the configured Gemini model for live mode only

## No-Key Demo

Start the complete synthetic-data demo without creating `.env` or calling a model:

```bash
./scripts/demo.sh
```

Open `http://localhost:8601`. The script creates temporary random local
credentials, starts an isolated Compose project, and forces `APP_MODE=recorded`
with an empty model key. Questions are matched to versioned, verified SQL
fixtures, then pass through the real SQL validator, query-plan guard, PostgreSQL
database, privacy masking, result formatting, charts, and feedback path.

Stop and remove the isolated demo with:

```bash
./scripts/demo.sh down
```

Recorded mode demonstrates the application workflow and controls. It is not
reported as live LLM accuracy.

See the [screenshot gallery and text walkthrough](interface.md) for example
queries, clarification, SQL inspection, charts, masking, and unsafe-request
rejection.

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

`/health` is the process liveness probe. `/ready` additionally validates the
agent configuration, business glossary, privacy policy, PostgreSQL connection,
configured tables and columns, and read-only role permissions. Compose waits for
this readiness check before starting the frontend.

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

## Database Onboarding

The onboarding command tests a PostgreSQL connection, verifies the current role,
lists available non-system schemas, and creates initial glossary and privacy
policy files for selected tables. It does not call Gemini, read table rows, use
database comments, or print the connection URL or credentials.

With the included Compose database running, execute the command from the local
virtual environment and override the container hostname:

```bash
DB_HOST=127.0.0.1 python -m database_setup check
DB_HOST=127.0.0.1 python -m database_setup configure
```

The interactive command asks which schemas and tables to allow. A deterministic
non-interactive setup is also available:

```bash
DB_HOST=127.0.0.1 python -m database_setup configure \
  --schema public \
  --table public.departments \
  --table public.employees \
  --table public.projects
```

The command creates `semantic_layer.generated.json` and
`privacy_policy.generated.json` with file mode `0600`. Both files are ignored by
Git and Docker build contexts because schema and column names may be sensitive.
Existing files are never overwritten unless `--force` is supplied.

Review the generated descriptions, aliases, allowlists, masks, and denylists
before activation. The generator identifies common credential, identity, contact,
and compensation column names, but application-specific data classification
still requires human review. It deliberately does not infer business metrics or
business terms.

Activate reviewed files in Compose by setting these local `.env` values:

```dotenv
SEMANTIC_LAYER_HOST_PATH=./semantic_layer.generated.json
PRIVACY_POLICY_HOST_PATH=./privacy_policy.generated.json
```

Restart the backend and verify the active configuration:

```bash
docker compose up -d --build --force-recreate backend frontend
docker compose exec backend python -m database_setup validate
```

The database role must be non-superuser, have no role/database creation,
replication, row-security bypass, schema creation, or table write privileges,
default to read-only transactions, and have `SELECT` only on every configured
table. Validation fails closed if a configured table or column is removed or
renamed.

## Business Glossary

[`semantic_layer.json`](../semantic_layer.json) defines table and column
descriptions, German and English aliases, reusable metrics, and business terms.
The included definitions cover employee headcount, average salary, payroll,
project budgets, and the `planned`, `active`, and `completed` project lifecycle.

The file is validated with Pydantic before use. Invalid or missing glossary data
fails closed and returns a generic configuration error. Set
`SEMANTIC_LAYER_PATH` to load a different validated glossary without changing
application code outside Compose. In Compose, use `SEMANTIC_LAYER_HOST_PATH` to
mount a reviewed file read-only.

## Ambiguity and Privacy

[`privacy_policy.json`](../privacy_policy.json) defines table and column allowlists,
denylists, explicit masks, restricted question terms, and automatic masking.
Pydantic validates the policy and SQLGlot enforces it independently of the model.
Set `PRIVACY_POLICY_PATH` to load another policy outside Compose. In Compose, use
`PRIVACY_POLICY_HOST_PATH` to mount a reviewed file read-only.

The default policy allows the three synthetic tables only in the `public` schema,
blocks requests for secret concepts such as password hashes and social-security
numbers, and automatically masks direct email, phone, identifier, and salary
outputs. Generated policies also deny discovered secret-like columns. Whole-row
values and collection aggregates are rejected. Scalar salary averages and totals
remain visible only when their query enforces the configured minimum non-null
cohort size. Set `masking.allow_aggregates` to `false` for stricter masking.

Ambiguity detection runs before the model. Requests with an unclear compensation
basis, date range, aggregation, or department return a focused clarification
question and consume no model tokens.

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

## Optional pgAdmin

Set `PGADMIN_DEFAULT_PASSWORD` to a unique value, then start the profile:

```bash
docker compose --profile admin up -d pgadmin
```

Open `http://localhost:5050`. PostgreSQL is reachable from pgAdmin at host
`postgres`, port `5432`.
