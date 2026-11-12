#!/usr/bin/env bash
# Stop whatever ./dashboard/start.sh started.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
for name in web api; do
  f=".pids/$name"
  if [ -f "$f" ]; then
    pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
      echo "Stopped $name (pid $pid)."
    fi
    rm -f "$f"
  fi
done
echo "Dashboard stopped."
