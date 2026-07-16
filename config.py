import os
from urllib.parse import quote_plus


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_app_secret_token() -> str:
    return require_env("APP_SECRET_TOKEN")


def get_database_url() -> str:
    explicit_url = os.environ.get("DATABASE_URL")
    if explicit_url:
        return explicit_url

    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_NAME", "company_data")
    db_user = os.environ.get("DB_USER", "ai_agent_user")
    db_password = require_env("AI_AGENT_DB_PASSWORD")

    return (
        "postgresql+psycopg2://"
        f"{quote_plus(db_user)}:{quote_plus(db_password)}@"
        f"{db_host}:{db_port}/{db_name}"
    )


def is_agent_verbose() -> bool:
    return os.environ.get("AGENT_VERBOSE", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_positive_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc

    if value < 1:
        raise RuntimeError(f"{name} must be greater than zero.")

    return value


def get_rate_limit_per_minute() -> int:
    return _get_positive_int("RATE_LIMIT_PER_MINUTE", 12)


def get_max_result_rows() -> int:
    return _get_positive_int("MAX_RESULT_ROWS", 100)


def get_agent_recursion_limit() -> int:
    return _get_positive_int("AGENT_RECURSION_LIMIT", 16)
