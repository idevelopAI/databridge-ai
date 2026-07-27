# ADR-0003: Privacy-Safe Observability

- Status: Accepted
- Date: 2026-07-27

## Context

Latency, token usage, tool outcomes, SQL duration, and rejection counts are useful
for operating and evaluating an agent. Prompts, generated SQL, tool arguments,
credentials, and database rows can contain sensitive information and should not
become a second data store through logs or metric labels.

## Decision

Structured events and Prometheus metrics use bounded metadata only:

- server-generated request IDs
- endpoint and outcome enums
- model, tool, and SQL durations
- input and output token counts
- tool-call counts
- bounded rejection reason codes

Content capture is disabled by default. Request text, SQL, credentials, tool
arguments, model answers, and returned rows are excluded from telemetry.
Framework verbose logging remains disabled. Reviewed feedback is a separate,
explicit local persistence action with restrictive file permissions.

## Consequences

- Aggregate behavior can be monitored without retaining database content.
- Debugging content-specific failures may require a deliberate local
  reproduction.
- New telemetry fields require a privacy review and cardinality check.
- Exported feedback and explicitly content-bearing evaluation reports must be
  handled as sensitive local artifacts.
