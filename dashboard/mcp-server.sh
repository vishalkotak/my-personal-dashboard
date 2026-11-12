#!/usr/bin/env bash
# Starts the health MCP server (stdio) for Claude Code, the Claude desktop app, or any MCP client.
#
#   claude mcp add health --scope user -- /absolute/path/to/dashboard/mcp-server.sh
#
# First run installs its dependencies into dashboard/backend/.venv. It reads dashboard/.env and
# uses the read-only database login. Nothing but the MCP protocol may be printed on stdout.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/backend"
if [ ! -x .venv/bin/python ]; then
  echo "Run ./dashboard/start.sh (or desktop/build.sh) once first to create the Python environment." >&2
  exit 1
fi
if [ ! -f .venv/.agent-installed ] || [ requirements-agent.txt -nt .venv/.agent-installed ]; then
  .venv/bin/pip install --quiet --disable-pip-version-check -r requirements-agent.txt >&2
  touch .venv/.agent-installed
fi
exec .venv/bin/python -m app.mcp_server
