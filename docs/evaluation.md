# Evaluation

[Back to the README](../README.md)

The versioned evaluation dataset contains 40 representative German and English
questions plus 12 unsafe SQL cases. Offline mode executes verified canonical SQL
against PostgreSQL, checks result equivalence, records latency, and confirms that
unsafe statements are rejected. It never calls Gemini:

```bash
docker compose exec backend python -m evaluation.run
```

The committed [`recorded-report.json`](../evaluation/recorded-report.json) was
measured inside the isolated recorded-mode Compose stack:

| Metric | Result |
| --- | ---: |
| Recorded execution success | 40/40 (100%) |
| Recorded result equivalence | 40/40 (100%) |
| Unsafe-query rejection | 12/12 (100%) |
| Recorded p50 / p95 latency | 1 ms / 3 ms |
| Recorded model tokens | 0 |
| Recorded estimated cost/query | $0.000000 |
| Live Gemini result equivalence | Not run |
| Automated tests | 140 passed |
| Backend test coverage | 82% |

Reproduce the recorded application-path measurement without a provider call:

```bash
docker compose exec backend python -m evaluation.run --recorded
```

This deterministic baseline validates the fixture, database path, and execution
controls; it is not presented as model accuracy. Live Text-to-SQL evaluation is
explicitly opt-in and calls the configured Gemini model once or more per selected
case. For accurate comparison, accepted read-only SQL is replayed without display
masking in memory; run this mode only against the included synthetic evaluation
database:

```bash
docker compose exec backend python -m evaluation.run --live --limit 5 \
  --max-cost-usd 0.05
```

Use `--case CASE_ID` to select specific cases and `--minimum-equivalence` to set
a failure threshold. The evaluator estimates cost from provider-reported token
usage and configurable input/output prices. The cost cap prevents subsequent
cases from starting after the configured amount is reached; provider billing
remains authoritative.

Save and copy a report from the non-root backend container with:

```bash
docker compose exec backend python -m evaluation.run --output /tmp/evaluation-report.json
docker compose cp backend:/tmp/evaluation-report.json ./evaluation-report.json
```

Reports omit questions, model answers, database rows, and generated SQL by
default. SQL can be included only with the explicit `--include-sql` option. The
dataset design follows the execution-based evaluation direction represented by
[Spider 2.0](https://arxiv.org/abs/2411.07763).
