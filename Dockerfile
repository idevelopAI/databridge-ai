FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --requirement requirements.txt

COPY agent.py ambiguity.py config.py database.py feedback.py main.py observability.py ./
COPY privacy_policy.py privacy_policy.json query_log.py query_plan.py rate_limit.py ./
COPY result_formatting.py schema_service.py semantic_layer.py semantic_layer.json ./
COPY sql_safety.py sql_tools.py ./
COPY evaluation/ evaluation/

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir --parents /data \
    && chown appuser:appuser /data \
    && chmod 0700 /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
