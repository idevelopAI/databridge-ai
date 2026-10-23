# Contributing

## Development Workflow

1. Create a focused branch from `main`.
2. Keep credentials in `.env`; never commit secrets or real database records.
3. Add or update tests for behavioral changes.
4. Run the lint, formatting, coverage, dependency audit, and Compose checks in the
   [development guide](docs/development.md#development) before opening a pull request.
5. Explain the behavior changed, security implications, and verification performed.

Keep changes narrowly scoped. Do not weaken the SQL parser, database permissions,
result limits, authentication, or secret-isolation controls without documenting a
replacement control and its tests.

Use `./scripts/demo.sh` to verify the full local workflow without a provider key.
Recorded mode must remain deterministic and must not initialize a model client.
