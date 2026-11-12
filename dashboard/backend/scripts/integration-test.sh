#!/usr/bin/env bash
# Runs the integration tests against a throwaway Postgres 17 in Docker, then removes it.
# Usage: scripts/integration-test.sh   (from dashboard/backend, with the venv set up)
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="healthsync-dashboard-test-$$"
PW="$(openssl rand -hex 16)"
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD="$PW" -p 127.0.0.1::5432 postgres:17-alpine >/dev/null
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

PORT="$(docker port "$NAME" 5432/tcp | head -1 | sed 's/.*://')"
for _ in $(seq 1 60); do
  docker exec "$NAME" pg_isready -U postgres -h 127.0.0.1 >/dev/null 2>&1 && break
  sleep 0.5
done

TEST_DATABASE_ADMIN_URL="postgresql://postgres:${PW}@127.0.0.1:${PORT}/postgres" \
  .venv/bin/pytest tests/test_integration_pg.py "$@"
