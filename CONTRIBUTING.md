# Contributing

## Development Workflow

1. Create a focused branch from `main`.
2. Keep credentials in `.env`; never commit secrets or real database records.
3. Add or update tests for behavioral changes.
4. Run the required checks before opening a pull request:

   ```bash
   ruff check .
   ruff format --check .
   python -m compileall -q agent.py app.py config.py csv_export.py database.py \
     main.py query_log.py rate_limit.py result_formatting.py schema_service.py \
     sql_safety.py sql_tools.py tests
   pytest -q
   docker compose config --quiet
   ```

5. Explain the behavior changed, security implications, and verification performed.

Keep changes narrowly scoped. Do not weaken the SQL parser, database permissions,
result limits, authentication, or secret-isolation controls without documenting a
replacement control and its tests.
