"""MCP server: talk to your health data from Claude Code, the Claude desktop app, or any MCP client.

    dashboard/backend/.venv/bin/python -m app.mcp_server        # stdio; the client starts it

It reads dashboard/.env and uses the dashboard's read-only database login, so it can
look but never change anything. See dashboard/README section "Talk to your data".
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as MCPToolError

from .agent_tools import DESCRIPTIONS, HealthTools, ToolError
from .api import build_source
from .catalog import load_catalog
from .config import load_settings

# stdout carries the MCP protocol; anything else printed there would corrupt it.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

INSTRUCTIONS = """\
You are talking with the person whose Apple Health data this is. Answer from their data:
call the tools instead of guessing, and quote the numbers you used with their dates.

- Start with list_available_data if you don't know what exists or how fresh it is. Say so
  plainly when data is missing or stale instead of drawing conclusions from gaps.
- Ground advice in longevity_status and get_research, and cite the study it comes from.
  These are observational associations, not guarantees; say so when it matters.
- Use remember for context they share (illness, injury, travel, goals, experiments) and
  recall it before judging a period, so a flu week isn't scolded as laziness.
- You are not a doctor. For anything that looks medical (a sudden resting-HR jump, very low
  blood oxygen, irregular rhythm, chest pain, fainting), tell them to talk to a clinician.
"""


def _call(fn, *args):
    """Bad arguments reach the model with their message, so it can fix the call. Anything
    else is a crash: the MCP library reports it without details, which keeps database
    errors and connection strings out of the conversation."""
    try:
        return fn(*args)
    except ToolError as e:
        raise MCPToolError(str(e)) from e


def build_server() -> MCPServer:
    settings = load_settings()
    tools = HealthTools(settings, build_source(settings), load_catalog(settings.types_path))
    server = MCPServer("health", instructions=INSTRUCTIONS)

    @server.tool(description=DESCRIPTIONS["list_available_data"])
    def list_available_data() -> dict[str, Any]:
        return _call(tools.list_available_data)

    @server.tool(description=DESCRIPTIONS["get_metric"])
    def get_metric(metric: str, start: str | None = None, end: str | None = None,
                   granularity: str = "auto") -> dict[str, Any]:
        return _call(tools.get_metric, metric, start, end, granularity)

    @server.tool(description=DESCRIPTIONS["compare_periods"])
    def compare_periods(metric: str, a_start: str, a_end: str, b_start: str, b_end: str) -> dict[str, Any]:
        return _call(tools.compare_periods, metric, a_start, a_end, b_start, b_end)

    @server.tool(description=DESCRIPTIONS["get_sleep"])
    def get_sleep(start: str | None = None, end: str | None = None) -> dict[str, Any]:
        return _call(tools.get_sleep, start, end)

    @server.tool(description=DESCRIPTIONS["get_workouts"])
    def get_workouts(start: str | None = None, end: str | None = None) -> dict[str, Any]:
        return _call(tools.get_workouts, start, end)

    @server.tool(description=DESCRIPTIONS["longevity_status"])
    def longevity_status() -> dict[str, Any]:
        return _call(tools.longevity_status)

    @server.tool(description=DESCRIPTIONS["get_research"])
    def get_research(marker: str | None = None) -> dict[str, Any]:
        return _call(tools.get_research, marker)

    @server.tool(description=DESCRIPTIONS["remember"])
    def remember(note: str) -> dict[str, Any]:
        return _call(tools.remember, note)

    @server.tool(description=DESCRIPTIONS["recall"])
    def recall() -> dict[str, Any]:
        return _call(tools.recall)

    @server.tool(description=DESCRIPTIONS["forget"])
    def forget(note_id: int) -> dict[str, Any]:
        return _call(tools.forget, note_id)

    return server


def main() -> None:
    build_server().run()  # stdio


if __name__ == "__main__":
    main()
