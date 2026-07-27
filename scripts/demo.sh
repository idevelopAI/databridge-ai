#!/bin/sh
set -eu

project_name="databridge-recorded-demo"
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

export APP_MODE=recorded
export GOOGLE_API_KEY=
export APP_SECRET_TOKEN=$(openssl rand -hex 32)
export POSTGRES_PASSWORD=$(openssl rand -hex 32)
export AI_AGENT_DB_PASSWORD=$(openssl rand -hex 32)
export PGADMIN_DEFAULT_PASSWORD=$(openssl rand -hex 32)
export BACKEND_PORT=${BACKEND_PORT:-8100}
export FRONTEND_PORT=${FRONTEND_PORT:-8601}
export POSTGRES_PORT=${POSTGRES_PORT:-55432}

compose() {
    docker compose \
        --project-name "$project_name" \
        --file "$project_dir/docker-compose.yml" \
        --file "$project_dir/docker-compose.demo.yml" \
        "$@"
}

if [ "${1:-up}" = "down" ]; then
    compose down --volumes --remove-orphans
    exit 0
fi

compose down --volumes --remove-orphans
compose up --detach --build --wait

printf 'DataBridge AI recorded demo: http://localhost:%s\n' "$FRONTEND_PORT"
printf 'Stop it with: ./scripts/demo.sh down\n'
