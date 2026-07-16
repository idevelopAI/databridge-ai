# Changelog

All notable changes are documented in this file.

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
