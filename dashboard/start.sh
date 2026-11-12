#!/usr/bin/env bash
# Start the dashboard: backend (FastAPI) + frontend (Vite), both on 127.0.0.1 only.
#
#   ./dashboard/start.sh          # real data (needs dashboard/.env with DATABASE_URL)
#   DEMO=1 ./dashboard/start.sh   # synthetic demo data, no database needed
#
# First run installs dependencies into dashboard/backend/.venv and
# dashboard/frontend/node_modules. Logs go to dashboard/logs/. Stop with ./dashboard/stop.sh.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
mkdir -p logs .pids

# Ports can be overridden in dashboard/.env (API_PORT / FRONTEND_PORT) or the environment.
env_value() { [ -f .env ] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
API_PORT="${API_PORT:-$(env_value API_PORT)}"; API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-$(env_value FRONTEND_PORT)}"; FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export API_PORT FRONTEND_PORT

running() { [ -f ".pids/$1" ] && kill -0 "$(cat ".pids/$1")" 2>/dev/null; }

if [ "${DEMO:-$(env_value DEMO)}" != "1" ] && [ ! -f .env ]; then
  echo "No dashboard/.env yet."
  echo "  • To try it with synthetic data:  DEMO=1 ./dashboard/start.sh"
  echo "  • To use your data: cp dashboard/.env.example dashboard/.env and fill in DATABASE_URL"
  echo "    (see dashboard/sql/readonly_role.sql)."
  exit 1
fi

# ---------------------------------------------------------------- backend
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "Python 3.11+ is required (brew install python@3.12)."; exit 1; }

if [ ! -x backend/.venv/bin/python ]; then
  echo "Setting up Python environment (first run)…"
  "$PY" -m venv backend/.venv
fi
if [ ! -f backend/.venv/.installed ] || [ backend/requirements.txt -nt backend/.venv/.installed ]; then
  backend/.venv/bin/pip install --quiet --disable-pip-version-check -r backend/requirements.txt
  touch backend/.venv/.installed
fi

if running api; then
  echo "Backend already running (pid $(cat .pids/api))."
else
  cd "$DIR/backend"
  nohup .venv/bin/python -m app </dev/null >"$DIR/logs/api.log" 2>&1 &
  echo $! >"$DIR/.pids/api"
  cd "$DIR"
fi

# ---------------------------------------------------------------- frontend
command -v npm >/dev/null || { echo "Node.js 20.19+ is required (brew install node)."; exit 1; }
if [ ! -d frontend/node_modules ] || [ frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]; then
  echo "Installing frontend dependencies (first run)…"
  (cd frontend && npm ci --no-audit --no-fund --loglevel=error)
fi
if running web; then
  echo "Frontend already running (pid $(cat .pids/web))."
else
  cd "$DIR/frontend"
  nohup node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort </dev/null >"$DIR/logs/web.log" 2>&1 &
  echo $! >"$DIR/.pids/web"
  cd "$DIR"
fi

# ---------------------------------------------------------------- wait until both answer
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
    echo
    echo "Dashboard is running:  http://localhost:$FRONTEND_PORT"
    curl -fsS "http://127.0.0.1:$API_PORT/api/health" | grep -q '"demo":true' && echo "(demo mode: synthetic data)"
    echo "Stop it with:          ./dashboard/stop.sh"
    exit 0
  fi
  if ! running api; then echo "Backend failed to start. Last lines of dashboard/logs/api.log:"; tail -20 logs/api.log; exit 1; fi
  if ! running web; then echo "Frontend failed to start. Last lines of dashboard/logs/web.log:"; tail -20 logs/web.log; exit 1; fi
  sleep 0.5
done
echo "Timed out waiting for the dashboard. Check dashboard/logs/."
exit 1
