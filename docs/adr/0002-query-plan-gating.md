# ADR-0002: PostgreSQL Query-Plan Gating

- Status: Accepted
- Date: 2026-07-27

## Context

A syntactically read-only query can still exhaust local resources through large
scans, excessive estimated result sizes, or Cartesian joins. Static SQL parsing
does not have PostgreSQL statistics or planner estimates.

## Decision

Every accepted PostgreSQL statement is checked with
`EXPLAIN (FORMAT JSON)` before execution. The guard rejects plans that exceed
configurable estimated total cost or row thresholds, large sequential scans, and
large unconditioned nested loops. It returns a generic reason to the user and
records only a bounded rejection code.

The guard does not use `EXPLAIN ANALYZE`, because analysis would execute the
statement. Server-side statement timeouts and result limits remain enabled after
the plan is accepted.

## Consequences

- Planner estimates provide an inexpensive workload-aware check.
- Estimates can be inaccurate when statistics are stale or data is skewed.
- Thresholds must be calibrated for each connected database.
- False rejections are preferable to silently running an unexpectedly expensive
  query in this local assistant.
