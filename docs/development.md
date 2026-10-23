# Development and Releases

[Back to the README](../README.md)

## Development

Create a virtual environment and install the pinned development dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
```

Run all local checks:

```bash
ruff check .
ruff format --check .
pip-audit --requirement requirements-dev.txt
pip-audit --requirement requirements-frontend.txt
python -m compileall -q agent.py app.py config.py csv_export.py database.py \
  ambiguity.py configuration_validation.py database_assurance.py \
  database_setup.py feedback.py main.py observability.py privacy_policy.py \
  query_log.py query_plan.py rate_limit.py recorded_demo.py \
  result_formatting.py schema_service.py semantic_layer.py sql_safety.py \
  sql_tools.py unsafe_intent.py evaluation tests
pytest -q --cov --cov-report=term-missing:skip-covered
docker compose config --quiet
```

Tests use isolated SQLite databases and mocked agents, so they do not call Gemini
or require PostgreSQL. CI enforces at least 80% backend coverage and runs the test
suite on Python 3.11, 3.12, and 3.13.

## Releases

Semantic version tags run the release workflow only after linting and tests pass.
The workflow builds the backend and frontend images, rejects fixable high and
critical vulnerabilities, publishes versioned images to GHCR, creates signed
provenance and SBOM attestations, and attaches SPDX SBOMs, Trivy reports, and
checksums to the GitHub release.

For version 1.2.0:

```bash
docker pull ghcr.io/idevelopai/databridge-ai-backend:1.2.0
docker pull ghcr.io/idevelopai/databridge-ai-frontend:1.2.0

gh attestation verify \
  oci://ghcr.io/idevelopai/databridge-ai-backend:1.2.0 \
  --repo idevelopAI/databridge-ai
```

Container packages and GitHub Actions are public repository services; no hosted
application or paid cloud infrastructure is required.
