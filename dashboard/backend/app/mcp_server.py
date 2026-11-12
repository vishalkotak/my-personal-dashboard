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

from .agent_tools import HealthTools, ToolError
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

    @server.tool()
    def list_available_data() -> dict[str, Any]:
        """List every kind of health data that exists, with sample counts and the date of the
        latest reading, plus today's date, the time zone, and the person's age. Call this first
        when unsure what data exists or whether it's up to date."""
        return _call(tools.list_available_data)

    @server.tool()
    def get_metric(metric: str, start: str | None = None, end: str | None = None,
                   granularity: str = "auto") -> dict[str, Any]:
        """One metric over a date range, as daily totals (steps, energy, distance), daily
        averages (heart rate, HRV, weight), or minutes per day (categories). `metric` is a short
        name (steps, distance, active_energy, heart_rate, resting_hr, hrv, body_mass, spo2,
        body_temp, bp_systolic, bp_diastolic) or any HealthKit identifier / name from
        list_available_data, e.g. "VO2 Max". Dates are YYYY-MM-DD; the default is the last 30
        days. granularity: auto (day ≤ 62 days, week ≤ 370, else month), day, week or month.
        Returns summary stats (mean, median, min, max) and one point per period."""
        return _call(tools.get_metric, metric, start, end, granularity)

    @server.tool()
    def compare_periods(metric: str, a_start: str, a_end: str, b_start: str, b_end: str) -> dict[str, Any]:
        """Compare a metric's mean daily value between period A and period B (YYYY-MM-DD).
        Use for before/after questions, e.g. HRV before vs. after starting a habit."""
        return _call(tools.compare_periods, metric, a_start, a_end, b_start, b_end)

    @server.tool()
    def get_sleep(start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Sleep per night (asleep hours, deep/REM/awake minutes, bedtime), or per week for
        ranges over 62 days, plus averages, nights under 7 h, and bedtime spread (regularity).
        A night is labelled with the date you woke up. Default: the last 30 nights."""
        return _call(tools.get_sleep, start, end)

    @server.tool()
    def get_workouts(start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Workouts in a date range: minutes and sessions by type and by week, strength-training
        minutes, and up to 30 recent sessions. Default: the last 30 days."""
        return _call(tools.get_workouts, start, end)

    @server.tool()
    def longevity_status() -> dict[str, Any]:
        """Where the person stands on each research-backed longevity marker (daily steps,
        weekly exercise, strength training, sleep duration and regularity, resting heart
        rate, VO2 max): current value, target, status (on_target / below_target /
        no_recent_data), and the study behind it. Use for "how am I doing" questions."""
        return _call(tools.longevity_status)

    @server.tool()
    def get_research(marker: str | None = None) -> dict[str, Any]:
        """The evidence behind the longevity targets: citation, key finding and link, for one
        marker (e.g. "sleep", "vo2max") or all of them."""
        return _call(tools.get_research, marker)

    @server.tool()
    def remember(note: str) -> dict[str, Any]:
        """Save context the person mentions that explains their data or shapes advice: an
        illness, injury, travel, a goal, an experiment they're running. Short, dated notes."""
        return _call(tools.remember, note)

    @server.tool()
    def recall() -> dict[str, Any]:
        """Every saved note, oldest first. Check before judging a period or giving advice."""
        return _call(tools.recall)

    @server.tool()
    def forget(note_id: int) -> dict[str, Any]:
        """Delete a saved note by id (from recall) when it's wrong or no longer relevant."""
        return _call(tools.forget, note_id)

    return server


def main() -> None:
    build_server().run()  # stdio


if __name__ == "__main__":
    main()
