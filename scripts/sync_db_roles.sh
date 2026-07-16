#!/usr/bin/env bash
set -euo pipefail

docker compose exec -T postgres sh -lc 'psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v ai_agent_password="$AI_AGENT_DB_PASSWORD" -v postgres_password="$POSTGRES_PASSWORD" -v database_name="$POSTGRES_DB" -v postgres_user="$POSTGRES_USER" <<'"'"'SQL'"'"'
ALTER ROLE ai_agent_user WITH PASSWORD :'"'"'ai_agent_password'"'"';
ALTER ROLE ai_agent_user SET default_transaction_read_only = on;
ALTER ROLE ai_agent_user SET statement_timeout = '"'"'10s'"'"';
ALTER ROLE ai_agent_user SET idle_in_transaction_session_timeout = '"'"'10s'"'"';
ALTER ROLE :"postgres_user" WITH PASSWORD :'"'"'postgres_password'"'"';
GRANT CONNECT ON DATABASE :"database_name" TO ai_agent_user;
GRANT USAGE ON SCHEMA public TO ai_agent_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_agent_user;
SQL'
