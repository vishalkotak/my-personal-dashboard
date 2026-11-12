"""Health tools for an AI agent: small, aggregated answers over the dashboard's data.

Shared by the MCP server (talk to your data from Claude Code or the Claude desktop app)
and, later, the dashboard's own chat tab. Two rules keep it safe and cheap:

* Read-only: it goes through the same Source as the dashboard, i.e. the read-only
  database login. The only thing it can write is the local notes file.
* Summaries, not samples: every answer is a handful of numbers (daily, weekly or
  monthly), never raw rows, so little of your health data leaves this machine.
"""

from __future__ import annotations

import json
import os
import statistics
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import hktypes as hk
from . import service
from .catalog import Catalog, TypeInfo
from .config import Settings
from .sources import Source

DASHBOARD_DIR = Path(__file__).resolve().parents[2]
RULES_PATH = DASHBOARD_DIR.parent / "apple-health-sync" / "HealthSync" / "LongevityRules.json"
NOTES_PATH = DASHBOARD_DIR / "agent-notes.json"  # gitignored

MAX_RANGE_DAYS = 3 * 366
MAX_NOTES, MAX_NOTE_CHARS = 200, 500
STALE_DAYS = 14  # a marker with no data this recent is reported as "no recent data"

VO2MAX = "HKQuantityTypeIdentifierVO2Max"
EXERCISE_TIME = "HKQuantityTypeIdentifierAppleExerciseTime"
STRENGTH_WORDS = ("strength", "core training")


class ToolError(ValueError):
    """A bad argument. The message is meant for the model, so it can correct itself."""


class HealthTools:
    def __init__(self, settings: Settings, source: Source, catalog: Catalog, notes_path: Path = NOTES_PATH):
        self.settings, self.src, self.catalog = settings, source, catalog
        self.tz = settings.tz
        self.notes_path = notes_path
        self._notes_lock = threading.Lock()

    # ------------------------------------------------------------------ helpers

    def today(self) -> date:
        return service.today_local(self.tz, self.settings.demo_now)

    def _range(self, start: str | None, end: str | None, default_days: int = 30) -> tuple[date, date]:
        try:
            to = date.fromisoformat(end) if end else self.today()
            frm = date.fromisoformat(start) if start else to - timedelta(days=default_days - 1)
        except ValueError as e:
            raise ToolError("Dates must be YYYY-MM-DD.") from e
        if frm > to:
            raise ToolError("start must be on or before end.")
        if (to - frm).days + 1 > MAX_RANGE_DAYS:
            raise ToolError(f"Ranges are limited to {MAX_RANGE_DAYS} days.")
        if frm < date(2000, 1, 1) or to > self.today() + timedelta(days=1):
            raise ToolError("Dates must be between 2000-01-01 and today.")
        return frm, to

    def _resolve(self, name: str) -> TypeInfo:
        """Short metric key ('steps'), HealthKit id, or a catalog name ('VO2 Max')."""
        m = hk.lookup_metric(name)
        info = self.catalog.get(m.hk_type if m else name)
        if info is None:
            low = name.strip().lower()
            info = next((t for t in self.catalog.by_id.values() if t.name.lower() == low), None)
        if info is None:
            raise ToolError(f"Unknown metric {name!r}. Call list_available_data to see what exists.")
        return info

    def _daily(self, info: TypeInfo, frm: date, to: date) -> tuple[list[tuple[str, float | None]], str, str]:
        """[(date, value)] with one value per day, plus (unit, aggregation)."""
        data = service.metric(self.src, info, frm, to, self.tz)
        key = {"sum": "value", "average": "avg", "duration": "minutes"}[data["aggregation"]]
        unit = data["display_unit"] or info.unit or ""
        return [(p["date"], p.get(key)) for p in data["points"]], unit, data["aggregation"]

    @staticmethod
    def _bucket(points: list[tuple[str, float | None]], granularity: str) -> list[dict[str, Any]]:
        if granularity == "day":
            # Days without data are left out (summary.days_in_range says how many there were).
            return [{"period": d, "value": _r(v)} for d, v in points if v is not None]
        groups: dict[str, list[float]] = {}
        for d, v in points:
            day = date.fromisoformat(d)
            k = (day - timedelta(days=day.weekday())).isoformat() if granularity == "week" else d[:7]
            groups.setdefault(k, [])
            if v is not None:
                groups[k].append(v)
        return [
            {"period": k, "value": _r(statistics.fmean(vs)) if vs else None, "days_with_data": len(vs)}
            for k, vs in groups.items()
        ]

    def _age(self) -> int | None:
        raw = (os.environ.get("BIRTH_MONTH") or "").strip()
        try:
            y, m = (int(x) for x in raw.split("-")[:2])
        except ValueError:
            return None
        t = self.today()
        return t.year - y - (1 if t.month < m else 0)

    # ------------------------------------------------------------------ tools

    def list_available_data(self) -> dict[str, Any]:
        """Which kinds of data exist, how much, and how recent."""
        rows = []
        for st in self.src.type_stats():
            info = self.catalog.get(st.type) or self.catalog.add_discovered(st.type, st.unit)
            rows.append({
                "metric": info.id,
                "name": info.name,
                "group": info.group,
                "samples": st.count,
                "latest": st.latest.date().isoformat() if st.latest else None,
            })
        rows.sort(key=lambda r: r["latest"] or "", reverse=True)
        return {
            "today": self.today().isoformat(),
            "time_zone": self.settings.tz_name,
            "age": self._age(),
            "short_names": sorted(hk.METRICS),
            "data": rows,
        }

    def get_metric(self, metric: str, start: str | None = None, end: str | None = None,
                   granularity: str = "auto") -> dict[str, Any]:
        """One metric over a date range, summarised per day, week or month."""
        info = self._resolve(metric)
        frm, to = self._range(start, end)
        days = (to - frm).days + 1
        if granularity == "auto":
            granularity = "day" if days <= 62 else "week" if days <= 370 else "month"
        if granularity not in ("day", "week", "month"):
            raise ToolError("granularity must be auto, day, week or month.")
        if granularity == "day" and days > 120:
            raise ToolError("Use week or month granularity for ranges over 120 days.")
        points, unit, agg = self._daily(info, frm, to)
        vals = [v for _, v in points if v is not None]
        return {
            "metric": info.name,
            "unit": unit,
            "per_day": {"sum": "daily total", "average": "daily average", "duration": "minutes per day"}[agg],
            "from": frm.isoformat(),
            "to": to.isoformat(),
            "granularity": granularity,
            "summary": {
                "mean": _r(statistics.fmean(vals)) if vals else None,
                "median": _r(statistics.median(vals)) if vals else None,
                "min": _r(min(vals)) if vals else None,
                "max": _r(max(vals)) if vals else None,
                "days_with_data": len(vals),
                "days_in_range": days,
            },
            "points": self._bucket(points, granularity),
        }

    def compare_periods(self, metric: str, a_start: str, a_end: str, b_start: str, b_end: str) -> dict[str, Any]:
        """Mean daily value of a metric in period A vs period B."""
        info = self._resolve(metric)
        out = {}
        for label, s, e in (("a", a_start, a_end), ("b", b_start, b_end)):
            frm, to = self._range(s, e)
            points, unit, _ = self._daily(info, frm, to)
            vals = [v for _, v in points if v is not None]
            out[label] = {"from": frm.isoformat(), "to": to.isoformat(),
                          "mean": _r(statistics.fmean(vals)) if vals else None, "days_with_data": len(vals)}
        a, b = out["a"]["mean"], out["b"]["mean"]
        return {
            "metric": info.name,
            "unit": unit,
            **out,
            "difference_b_minus_a": _r(b - a) if a is not None and b is not None else None,
            "percent_change": _r((b - a) / a * 100) if a and b is not None else None,
        }

    def get_sleep(self, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Sleep per night (or per week for long ranges), plus duration and regularity."""
        frm, to = self._range(start, end)
        nights = [n for n in service.sleep(self.src, frm, to, self.tz)["nights"] if n["has_data"]]
        bedtimes = [_minutes_after_noon(n["start"], self.tz) for n in nights if n.get("start")]
        asleep = [n["asleep_min"] / 60 for n in nights]
        summary = {
            "nights_with_data": len(nights),
            "avg_asleep_hours": _r(statistics.fmean(asleep), 2) if asleep else None,
            "nights_under_7h": sum(1 for h in asleep if h < 7),
            "avg_bedtime": _clock(statistics.fmean(bedtimes)) if bedtimes else None,
            "bedtime_spread_minutes": _r(statistics.pstdev(bedtimes), 0) if len(bedtimes) > 1 else None,
        }
        if (to - frm).days + 1 <= 62:
            per = [{
                "night": n["night"],
                "asleep_hours": _r(n["asleep_min"] / 60, 2),
                "deep_min": n["deep_min"], "rem_min": n["rem_min"], "awake_min": n["awake_min"],
                "bedtime": _clock(_minutes_after_noon(n["start"], self.tz)) if n.get("start") else None,
            } for n in nights]
        else:
            per = self._bucket([(n["night"], n["asleep_min"] / 60) for n in nights], "week")
        return {"from": frm.isoformat(), "to": to.isoformat(), "summary": summary, "nights": per,
                "note": "bedtime_spread_minutes is the standard deviation of bedtimes: lower is more regular."}

    def get_workouts(self, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Workouts by type and by week, and the most recent sessions."""
        frm, to = self._range(start, end)
        w = service.workouts(self.src, frm, to, self.tz)
        strength = sum(t["minutes"] for t in w["by_type"] if _is_strength(t["name"]))
        return {
            "from": frm.isoformat(), "to": to.isoformat(),
            "total_sessions": len(w["workouts"]),
            "strength_minutes": _r(strength),
            "by_type": w["by_type"],
            "weekly": w["weekly"],
            "recent": [{k: x[k] for k in ("date", "name", "duration_min")} for x in w["workouts"][:30]],
        }

    def longevity_status(self) -> dict[str, Any]:
        """Each research-backed marker: current value, target, status and the evidence."""
        rules = {r["id"]: r for r in _load_rules()["rules"]}
        today = self.today()
        last30 = (today - timedelta(days=30), today - timedelta(days=1))
        prior90 = (today - timedelta(days=120), today - timedelta(days=31))
        age = self._age()
        out = []

        def mean_of(type_id: str, frm: date, to: date) -> tuple[float | None, str | None]:
            info = self.catalog.get(type_id) or self.catalog.add_discovered(type_id, None)
            pts, _, _ = self._daily(info, frm, to)
            vals = [(d, v) for d, v in pts if v is not None]
            return (_r(statistics.fmean(v for _, v in vals)) if vals else None, vals[-1][0] if vals else None)

        def add(rule_id: str, value, unit: str, target: str, ok: bool | None, last: str | None, extra=None):
            r = rules.get(rule_id, {})
            stale = last is None or (today - date.fromisoformat(last)).days > STALE_DAYS
            out.append({
                "marker": r.get("title", rule_id),
                "value": value, "unit": unit, "target": target,
                "status": "no_recent_data" if stale else ("on_target" if ok else "below_target"),
                "last_data": last,
                **(extra or {}),
                "evidence": r.get("evidence"),
            })

        steps_target = rules["steps"]["target_age_60_plus" if age and age >= 60 else "target"]
        v, last = mean_of(hk.STEPS, *last30)
        add("steps", v, "steps/day (30-day avg)", f"≥ {steps_target}", v is not None and v >= steps_target, last)

        v, last = mean_of(EXERCISE_TIME, *last30)
        weekly = _r(v * 7) if v is not None else None
        add("exercise", weekly, "min/week (30-day avg)", f"≥ {rules['exercise']['target']}",
            weekly is not None and weekly >= rules["exercise"]["target"], last)

        # Any workout in the last 90 days shows workouts are syncing; strength is the last 4 weeks.
        recent = service.workouts(self.src, today - timedelta(days=90), today, self.tz)["workouts"]
        cutoff = (today - timedelta(days=28)).isoformat()
        strength_week = _r(sum(x["duration_min"] for x in recent
                               if x["date"] >= cutoff and _is_strength(x["name"])) / 4)
        add("strength", strength_week, "min/week (4-week avg)", f"≥ {rules['strength']['target']}",
            strength_week >= rules["strength"]["target"], recent[0]["date"] if recent else None,
            {"note": "Counts workouts logged as strength or core training."})

        s = self.get_sleep(last30[0].isoformat(), today.isoformat())["summary"]
        nights = [n for n in service.sleep(self.src, *last30, self.tz)["nights"] if n["has_data"]]
        add("sleep", s["avg_asleep_hours"], "hours/night (30-day avg)",
            f"≥ {rules['sleep']['min_hours']} h, bedtime spread ≤ {rules['sleep']['max_bedtime_shift_minutes']} min",
            s["avg_asleep_hours"] is not None and s["avg_asleep_hours"] >= rules["sleep"]["min_hours"]
            and (s["bedtime_spread_minutes"] or 0) <= rules["sleep"]["max_bedtime_shift_minutes"],
            nights[-1]["night"] if nights else None,
            {"bedtime_spread_minutes": s["bedtime_spread_minutes"]})

        for rule_id, type_id, unit, better in (("resting_hr", hk.RESTING_HR, "bpm", "lower"),
                                                ("vo2max", VO2MAX, "ml/kg/min", "higher")):
            now_v, last = mean_of(type_id, *last30)
            before, _ = mean_of(type_id, *prior90)
            trend = _r(now_v - before) if now_v is not None and before is not None else None
            ok = trend is None or (trend <= 0 if better == "lower" else trend >= 0)
            add(rule_id, now_v, f"{unit} (30-day avg)", f"{better} is better; watch the trend", ok, last,
                {"change_vs_prior_90_days": trend})

        return {"today": today.isoformat(), "age": age, "markers": out,
                "rules_last_reviewed": _load_rules().get("last_reviewed")}

    def get_research(self, marker: str | None = None) -> dict[str, Any]:
        """The evidence behind each marker (citation, claim, link)."""
        rules = _load_rules()
        items = [{"id": r["id"], "title": r["title"], **r["evidence"]} for r in rules["rules"]]
        if marker:
            items = [i for i in items if marker.lower() in (i["id"] + " " + i["title"]).lower()]
            if not items:
                raise ToolError(f"No research entry for {marker!r}.")
        return {"last_reviewed": rules.get("last_reviewed"), "research": items}

    # ------------------------------------------------------------------ notes (local file)

    def _read_notes(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.notes_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def remember(self, note: str) -> dict[str, Any]:
        """Save context the person mentions (illness, injury, goal, experiment)."""
        note = note.strip()
        if not note or len(note) > MAX_NOTE_CHARS:
            raise ToolError(f"A note must be 1–{MAX_NOTE_CHARS} characters.")
        with self._notes_lock:
            notes = self._read_notes()
            if len(notes) >= MAX_NOTES:
                raise ToolError("Notes are full; forget some first.")
            nid = max((n["id"] for n in notes), default=0) + 1
            notes.append({"id": nid, "saved": self.today().isoformat(), "note": note})
            self._write_notes(notes)
        return {"saved": nid}

    def recall(self) -> dict[str, Any]:
        """Everything saved with remember, oldest first."""
        return {"notes": self._read_notes()}

    def forget(self, note_id: int) -> dict[str, Any]:
        with self._notes_lock:
            notes = self._read_notes()
            kept = [n for n in notes if n["id"] != note_id]
            if len(kept) == len(notes):
                raise ToolError(f"No note with id {note_id}.")
            self._write_notes(kept)
        return {"forgotten": note_id}

    def _write_notes(self, notes: list[dict[str, Any]]) -> None:
        """Atomic write, readable only by you (notes can be as personal as the data)."""
        tmp = self.notes_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(notes, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(self.notes_path)


# ---------------------------------------------------------------------- module helpers


def _r(x: float | None, nd: int = 1) -> float | None:
    return None if x is None else round(x, nd)


def _is_strength(name: str) -> bool:
    return any(w in name.lower() for w in STRENGTH_WORDS)


def _minutes_after_noon(iso: str, tz) -> float:
    """Bedtime as minutes after the previous noon, so 23:30 and 00:30 average sensibly."""
    t = datetime.fromisoformat(iso).astimezone(tz)
    m = t.hour * 60 + t.minute
    return m - 720 if m >= 720 else m + 720


def _clock(minutes_after_noon: float) -> str:
    m = int(round(minutes_after_noon)) + 720
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


_rules_cache: dict[str, Any] | None = None


def _load_rules() -> dict[str, Any]:
    global _rules_cache
    if _rules_cache is None:
        _rules_cache = json.loads(RULES_PATH.read_text())
    return _rules_cache


# ---------------------------------------------------------------------- tool specs (shared)

_DATE = {"type": "string", "description": "YYYY-MM-DD"}

# One description per tool, used by the MCP server and by the in-app Coach alike.
TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "list_available_data",
     "description": "List every kind of health data that exists, with sample counts and the date of the "
                    "latest reading, plus today's date, the time zone, and the person's age. Call this first "
                    "when unsure what data exists or whether it's up to date.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_metric",
     "description": "One metric over a date range, as daily totals (steps, energy, distance), daily averages "
                    "(heart rate, HRV, weight), or minutes per day (categories). `metric` is a short name "
                    "(steps, distance, active_energy, heart_rate, resting_hr, hrv, body_mass, spo2, body_temp, "
                    "bp_systolic, bp_diastolic) or any HealthKit identifier / name from list_available_data, "
                    "e.g. \"VO2 Max\". The default range is the last 30 days. granularity: auto (day ≤ 62 days, "
                    "week ≤ 370, else month), day, week or month. Returns summary stats and one point per period.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["metric"], "properties": {
         "metric": {"type": "string"}, "start": _DATE, "end": _DATE,
         "granularity": {"type": "string", "enum": ["auto", "day", "week", "month"]}}}},
    {"name": "compare_periods",
     "description": "Compare a metric's mean daily value between period A and period B. Use for before/after "
                    "questions, e.g. HRV before vs. after starting a habit.",
     "input_schema": {"type": "object", "additionalProperties": False,
                      "required": ["metric", "a_start", "a_end", "b_start", "b_end"],
                      "properties": {"metric": {"type": "string"}, "a_start": _DATE, "a_end": _DATE,
                                     "b_start": _DATE, "b_end": _DATE}}},
    {"name": "get_sleep",
     "description": "Sleep per night (asleep hours, deep/REM/awake minutes, bedtime), or per week for ranges "
                    "over 62 days, plus averages, nights under 7 h, and bedtime spread (regularity). A night is "
                    "labelled with the date you woke up. Default: the last 30 nights.",
     "input_schema": {"type": "object", "additionalProperties": False,
                      "properties": {"start": _DATE, "end": _DATE}}},
    {"name": "get_workouts",
     "description": "Workouts in a date range: minutes and sessions by type and by week, strength-training "
                    "minutes, and up to 30 recent sessions. Default: the last 30 days.",
     "input_schema": {"type": "object", "additionalProperties": False,
                      "properties": {"start": _DATE, "end": _DATE}}},
    {"name": "longevity_status",
     "description": "Where the person stands on each research-backed longevity marker (daily steps, weekly "
                    "exercise, strength training, sleep duration and regularity, resting heart rate, VO2 max): "
                    "current value, target, status (on_target / below_target / no_recent_data), and the study "
                    "behind it. Use for \"how am I doing\" questions.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_research",
     "description": "The evidence behind the longevity targets: citation, key finding and link, for one marker "
                    "(e.g. \"sleep\", \"vo2max\") or all of them.",
     "input_schema": {"type": "object", "additionalProperties": False,
                      "properties": {"marker": {"type": "string"}}}},
    {"name": "remember",
     "description": "Save context the person mentions that explains their data or shapes advice: an illness, "
                    "injury, travel, a goal, an experiment they're running. Short, dated notes.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["note"],
                      "properties": {"note": {"type": "string"}}}},
    {"name": "recall",
     "description": "Every saved note, oldest first. Check before judging a period or giving advice.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "forget",
     "description": "Delete a saved note by id (from recall) when it's wrong or no longer relevant.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["note_id"],
                      "properties": {"note_id": {"type": "integer"}}}},
]
DESCRIPTIONS = {s["name"]: s["description"] for s in TOOL_SPECS}
_SPECS = {s["name"]: s for s in TOOL_SPECS}
_JSON_TYPES = {"string": str, "integer": int}


def call_tool(tools: HealthTools, name: str, args: Any) -> dict[str, Any]:
    """Run a tool from model-supplied arguments, checked against its schema first.

    Raises ToolError for anything malformed, so callers can hand the message back to the model.
    """
    spec = _SPECS.get(name)
    if spec is None:
        raise ToolError(f"No tool named {name!r}.")
    if not isinstance(args, dict):
        raise ToolError("Tool input must be a JSON object.")
    schema = spec["input_schema"]
    props = schema.get("properties", {})
    unknown = set(args) - set(props)
    missing = [k for k in schema.get("required", []) if k not in args]
    if unknown or missing:
        raise ToolError(f"Unexpected {sorted(unknown)} / missing {missing} arguments for {name}.")
    for k, v in args.items():
        want = _JSON_TYPES[props[k]["type"]]
        if v is not None and (not isinstance(v, want) or isinstance(v, bool)):
            raise ToolError(f"{k} must be a {props[k]['type']}.")
        if "enum" in props[k] and v not in props[k]["enum"]:
            raise ToolError(f"{k} must be one of {props[k]['enum']}.")
    return getattr(tools, name)(**args)
