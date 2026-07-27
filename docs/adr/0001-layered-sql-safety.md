# ADR-0001: Layered SQL Safety

- Status: Accepted
- Date: 2026-07-27

## Context

An LLM can generate invalid, expensive, or destructive SQL. Prompt instructions
alone are not an authorization boundary, and a parser check alone cannot protect
against every database-side capability or configuration error.

## Decision

DataBridge AI uses independent controls that fail closed:

1. Reject explicit data-modification intent before the agent runs.
2. Parse generated SQL with SQLGlot using the PostgreSQL dialect.
3. Accept exactly one read-only query and reject comments, locking clauses,
   data-modifying CTEs, and disallowed functions.
4. Enforce configured table and column policy on the parsed query.
5. Inspect the PostgreSQL plan before execution.
6. Execute through a restricted role with read-only transactions, statement
   timeouts, and bounded results.

Database permissions are the final enforcement boundary. Model prompts and tool
descriptions explain the policy but do not replace any control.

## Consequences

- A failure in one layer does not automatically grant write access.
- Some valid PostgreSQL features are intentionally unavailable.
- Policy and parser changes require adversarial tests.
- The local shared API token is not sufficient for a public or multi-user
  deployment.
