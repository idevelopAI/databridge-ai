FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --requirement requirements.txt \
    && pip uninstall --yes setuptools

COPY agent.py ambiguity.py config.py database.py feedback.py main.py observability.py ./
COPY privacy_policy.py privacy_policy.json query_log.py query_plan.py rate_limit.py ./
COPY recorded_demo.py result_formatting.py schema_service.py semantic_layer.py ./
COPY semantic_layer.json sql_safety.py sql_tools.py unsafe_intent.py ./
COPY evaluation/ evaluation/

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir --parents /data \
    && chown appuser:appuser /data \
    && chmod 0700 /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
