"""The agent's health tools, run against the deterministic demo data."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent_tools import HealthTools, ToolError
from app.catalog import load_catalog
from app.config import Settings
from app.demo import UNITS, generate
from app.sources import MemorySource

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 11, 18, 0, tzinfo=LA)


@pytest.fixture(scope="module")
def settings():
    return Settings(demo=True, database_url=None, tz_name="America/Los_Angeles", user_id=None,
                    frontend_origins=(), port=0, statement_timeout_ms=1000, demo_now=NOW)


@pytest.fixture(scope="module")
def source(settings):
    return MemorySource(generate(now=NOW, tz=LA), settings, units=UNITS)


@pytest.fixture()
def tools(settings, source, tmp_path):
    return HealthTools(settings, source, load_catalog(settings.types_path), notes_path=tmp_path / "notes.json")


def test_metric_defaults_to_last_30_days_daily(tools):
    out = tools.get_metric("steps")
    assert (out["from"], out["to"], out["granularity"]) == ("2026-10-13", "2026-11-11", "day")
    assert out["summary"]["days_in_range"] == 30
    assert out["summary"]["mean"] > 1000
    assert all(p["value"] is not None for p in out["points"])  # empty days are left out


def test_long_ranges_are_bucketed_and_stay_small(tools):
    assert tools.get_metric("resting_hr", "2025-12-01", "2026-11-11")["granularity"] == "week"  # auto
    out = tools.get_metric("resting_hr", "2025-12-01", "2026-11-11", "month")
    assert len(out["points"]) == 12
    assert len(json.dumps(out)) < 3000  # a year of data answered in a few KB


def test_metric_names_resolve_by_key_id_or_name(tools):
    assert tools.get_metric("hrv")["metric"] == tools.get_metric("HKQuantityTypeIdentifierHeartRateVariabilitySDNN")["metric"]
    with pytest.raises(ToolError, match="list_available_data"):
        tools.get_metric("vibes")


@pytest.mark.parametrize("args, msg", [
    (("steps", "yesterday"), "YYYY-MM-DD"),
    (("steps", "2026-11-10", "2026-11-01"), "on or before"),
    (("steps", "2025-01-01", "2026-11-01", "day"), "week or month"),
    (("steps", "1990-01-01", "1990-02-01"), "between"),
])
def test_bad_arguments_explain_themselves(tools, args, msg):
    with pytest.raises(ToolError, match=msg):
        tools.get_metric(*args)


def test_compare_periods(tools):
    out = tools.compare_periods("steps", "2026-09-01", "2026-09-30", "2026-10-01", "2026-10-31")
    assert out["a"]["mean"] and out["b"]["mean"]
    assert out["difference_b_minus_a"] == pytest.approx(out["b"]["mean"] - out["a"]["mean"], abs=0.2)


def test_sleep_summary_and_regularity(tools):
    s = tools.get_sleep()["summary"]
    assert 4 < s["avg_asleep_hours"] < 10
    assert s["bedtime_spread_minutes"] is not None
    assert len(s["avg_bedtime"]) == 5  # "HH:MM"


def test_longevity_status_reports_every_marker_with_evidence(tools):
    out = tools.longevity_status()
    names = [m["marker"] for m in out["markers"]]
    assert {"Daily steps", "Sleep", "Resting heart rate"} <= set(names)
    for m in out["markers"]:
        assert m["status"] in {"on_target", "below_target", "no_recent_data"}
        assert m["evidence"]["url"].startswith("https://")


def test_notes_round_trip_and_are_private(tools):
    nid = tools.remember("Had the flu Nov 3–6")["saved"]
    assert tools.recall()["notes"][0]["note"] == "Had the flu Nov 3–6"
    assert oct(tools.notes_path.stat().st_mode & 0o777) == "0o600"
    tools.forget(nid)
    assert tools.recall()["notes"] == []
    with pytest.raises(ToolError):
        tools.remember("x" * 501)
