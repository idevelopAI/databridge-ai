#!/usr/bin/env bash
set -euo pipefail

: "${AI_AGENT_DB_PASSWORD:?AI_AGENT_DB_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v ai_agent_password="$AI_AGENT_DB_PASSWORD" \
  -v database_name="$POSTGRES_DB" <<'SQL'
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS departments CASCADE;
DROP TABLE IF EXISTS projects CASCADE;

CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    salary DECIMAL(10, 2),
    department_id INT REFERENCES departments(id)
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    budget DECIMAL(10, 2)
);

INSERT INTO departments (name) VALUES ('Sales'), ('Engineering'), ('HR');

INSERT INTO employees (name, salary, department_id) VALUES
('Alice Smith', 75000, 1),
('Bob Jones', 120000, 2),
('Charlie Brown', 60000, 3),
('David Müller', 95000, 2);

INSERT INTO projects (name, budget) VALUES
('DataBridge AI', 150000),
('Project Simon', 500000);

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ai_agent_user') THEN
    CREATE ROLE ai_agent_user LOGIN;
  END IF;
END
$$;

ALTER ROLE ai_agent_user WITH PASSWORD :'ai_agent_password';
ALTER ROLE ai_agent_user SET default_transaction_read_only = on;
ALTER ROLE ai_agent_user SET statement_timeout = '10s';
ALTER ROLE ai_agent_user SET idle_in_transaction_session_timeout = '10s';
GRANT CONNECT ON DATABASE :"database_name" TO ai_agent_user;
GRANT USAGE ON SCHEMA public TO ai_agent_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_agent_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ai_agent_user;
SQL
