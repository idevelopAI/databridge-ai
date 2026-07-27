# Changelog

All notable changes are documented in this file.

## 1.2.0 - 2026-07-27

### Added

- Bilingual deterministic ambiguity detection with no model call for unclear
  compensation, period, aggregation, or department requests
- Pydantic-validated table and column policy with SQLGlot enforcement and direct
  sensitive-value masking
- Server-generated request IDs, privacy-safe structured events, LangChain model
  and tool metadata, token usage, and authenticated Prometheus metrics
- Correct/incorrect query feedback stored locally in SQLite with reviewed-example
  JSONL export
- Isolated recorded-fixture demo mode that runs without an API key or model call
- Recorded application-path evaluation with p50/p95 latency, token totals, and
  estimated cost per query
- Deterministic unsafe modification-intent rejection before agent execution
- Architecture decision records for SQL safety, plan gating, and privacy-safe
  observability
- Repeatable 75-second demo sequence covering results, SQL, charts,
  clarification, masking, and unsafe-request rejection
- Reviewed 75-second MP4 demonstration captured from the synthetic no-key stack
- Tag-driven GHCR publication with SPDX SBOMs, Trivy vulnerability reports,
  checksums, and signed build and SBOM attestations

### Changed

- Policy checks now run both before the model and before generated SQL execution
- Direct salary, identifier, email, and phone outputs are masked before reaching
  the model, response history, CSV export, or feedback controls
- Expanded CI and Docker smoke checks for metrics and the new policy modules
- Live evaluation supports explicit cost caps and configurable token pricing

## 1.1.0 - 2026-07-21

### Added

- Validated business glossary with German and English aliases, metric definitions,
  project lifecycle terms, and trusted prompt context
- PostgreSQL query-plan guard with configurable cost, result-size, sequential-scan,
  and Cartesian-join thresholds
- Forty-case bilingual Text-to-SQL evaluation dataset and twelve unsafe-query cases
- Offline deterministic evaluation and explicitly opt-in Gemini evaluation commands
- Expanded synthetic departments, employees, and project lifecycle metadata

### Changed

- Added query-plan validation before accepted PostgreSQL statements are executed
- Extended CI with the deterministic PostgreSQL evaluation suite

## 1.0.0 - 2026-07-16

### Added

- English and German natural-language PostgreSQL chat
- Schema explorer with key and relationship metadata
- Structured query tables, charts, CSV exports, and SQL inspection
- SQLGlot query parsing and bounded execution results
- Restricted database role with read-only transactions and statement timeouts
- FastAPI authentication, request validation, rate limiting, and health endpoints
- Docker health checks, loopback-only ports, and optional pgAdmin profile
- Unit tests, linting, formatting checks, Docker smoke tests, and Dependabot

### Changed

- Migrated the agent and SQL tools to the current LangChain APIs
- Replaced raw SQL result strings with JSON-safe structured execution records
- Improved error handling so internal exceptions and credentials are not returned
  to the browser
