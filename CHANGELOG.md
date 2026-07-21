# Changelog

All notable changes are documented in this file.

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
