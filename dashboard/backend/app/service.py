"""Turns samples from a Source into the JSON-ready shapes the API returns.

All dates here are *local* dates in the configured time zone; all instants are UTC.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from . import hktypes as hk
from .dedupe import (
    daily_cumulative,
    daily_raw_sum,
    local_date,
    nightly_sleep,
    pair_blood_pressure,
)
from .sources import Source

APPROX_NOTE = (
    "Approximate: iPhone and Apple Watch both record this and the app doesn't upload "
    "which device each sample came from, so overlapping samples are de-duplicated by "
    "estimate rather than by source."
)


def local_midnight(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time(0), tzinfo=tz).astimezone(timezone.utc)


def local_noon(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time(12), tzinfo=tz).astimezone(timezone.utc)


def date_range(frm: date, to: date) -> list[date]:
    return [frm + timedelta(days=i) for i in range((to - frm).days + 1)]


def _r(x: float | None, nd: int = 1) -> float | None:
    return None if x is None else round(x, nd)


def today_local(tz: ZoneInfo, now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(tz).date()


# ---------------------------------------------------------------- per-type daily


def daily(src: Source, metric: hk.Metric, frm: date, to: date, tz: ZoneInfo) -> dict[str, Any]:
    start, end = local_midnight(frm, tz), local_midnight(to + timedelta(days=1), tz)
    days = date_range(frm, to)
    if metric.kind == "cumulative":
        samples = src.samples(metric.hk_type, start, end)
        dedup = daily_cumulative(samples, tz)
        # Raw sum only over samples that start inside the window, like SQL would.
        raw = daily_raw_sum([s for s in samples if start <= s.start < end], tz)
        nd = 0 if metric.key == "steps" else 1
        points = [
            {
                "date": d.isoformat(),
                "value": _r(dedup.get(d), nd) if d in dedup or d in raw else None,
                "raw_sum": _r(raw.get(d), nd),
            }
            for d in days
        ]
        return {
            "type": metric.key,
            "kind": "cumulative",
            "unit": metric.display_unit,
            "approximate": True,
            "note": APPROX_NOTE,
            "points": points,
        }

    stats = {s.day: s for s in src.daily_stats(metric.hk_type, start, end)}
    k = metric.scale
    nd = 1 if metric.key not in ("body_temp",) else 2
    points = []
    for d in days:
        s = stats.get(d)
        points.append(
            {
                "date": d.isoformat(),
                "avg": _r(s.avg * k, nd) if s else None,
                "min": _r(s.min * k, nd) if s else None,
                "max": _r(s.max * k, nd) if s else None,
                "last": _r(s.last * k, nd) if s else None,
                "count": s.count if s else 0,
            }
        )
    return {
        "type": metric.key,
        "kind": "discrete",
        "unit": metric.display_unit,
        "approximate": False,
        "points": points,
    }


# ---------------------------------------------------------------- sleep


def sleep(src: Source, frm: date, to: date, tz: ZoneInfo) -> dict[str, Any]:
    # Night D spans [D-1 12:00, D 12:00) local.
    start, end = local_noon(frm - timedelta(days=1), tz), local_noon(to, tz)
    samples = src.samples(hk.SLEEP, start, end)
    nights = {n.night: n for n in nightly_sleep(samples, tz) if frm <= n.night <= to}

    def m(x: float) -> float:
        return round(x / 60, 1)

    out = []
    for d in date_range(frm, to):
        n = nights.get(d)
        if n is None:
            out.append({"night": d.isoformat(), "has_data": False})
            continue
        out.append(
            {
                "night": d.isoformat(),
                "has_data": True,
                "asleep_min": m(n.asleep_s),
                "deep_min": m(n.deep_s),
                "core_min": m(n.core_s),
                "rem_min": m(n.rem_s),
                "unspecified_min": m(n.unspecified_s),
                "awake_min": m(n.awake_s),
                "in_bed_min": m(n.in_bed_s),
                "staged": (n.deep_s + n.core_s + n.rem_s) > 0,
                "start": n.start.isoformat() if n.start else None,
                "end": n.end.isoformat() if n.end else None,
            }
        )
    return {"nights": out}


# ---------------------------------------------------------------- workouts


def workouts(src: Source, frm: date, to: date, tz: ZoneInfo) -> dict[str, Any]:
    start, end = local_midnight(frm, tz), local_midnight(to + timedelta(days=1), tz)
    rows = [s for s in src.samples(hk.WORKOUT, start, end) if start <= s.start < end]
    items = []
    weekly: dict[date, dict[str, float]] = {}
    by_type: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "minutes": 0.0})

    # Every week touching the range, so the chart shows empty weeks too.
    wk = frm - timedelta(days=frm.weekday())
    while wk <= to:
        weekly[wk] = {"minutes": 0.0, "count": 0}
        wk += timedelta(days=7)

    for s in sorted(rows, key=lambda s: s.start, reverse=True):
        minutes = s.value / 60
        activity = (s.metadata or {}).get("activity_type")
        name = hk.workout_name(activity)
        items.append(
            {
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "date": local_date(s.start, tz).isoformat(),
                "duration_min": round(minutes, 1),
                "activity_type": int(activity) if str(activity or "").isdigit() else None,
                "name": name,
            }
        )
        d = local_date(s.start, tz)
        w = weekly[d - timedelta(days=d.weekday())]
        w["minutes"] += minutes
        w["count"] += 1
        by_type[name]["count"] += 1
        by_type[name]["minutes"] += minutes

    return {
        "workouts": items,
        "weekly": [
            {"week_start": k.isoformat(), "minutes": round(v["minutes"], 1), "count": int(v["count"])}
            for k, v in sorted(weekly.items())
        ],
        "by_type": sorted(
            (
                {"name": k, "count": int(v["count"]), "minutes": round(v["minutes"], 1)}
                for k, v in by_type.items()
            ),
            key=lambda x: -x["minutes"],
        ),
    }


# ---------------------------------------------------------------- heart & body


def heart(src: Source, frm: date, to: date, tz: ZoneInfo) -> dict[str, Any]:
    hr = daily(src, hk.METRICS["heart_rate"], frm, to, tz)["points"]
    rhr = daily(src, hk.METRICS["resting_hr"], frm, to, tz)["points"]
    hrv = daily(src, hk.METRICS["hrv"], frm, to, tz)["points"]
    return {
        "days": [
            {
                "date": a["date"],
                "hr_min": a["min"],
                "hr_avg": a["avg"],
                "hr_max": a["max"],
                "resting": b["avg"],
                "hrv": c["avg"],
            }
            for a, b, c in zip(hr, rhr, hrv)
        ]
    }


def body(src: Source, frm: date, to: date, tz: ZoneInfo) -> dict[str, Any]:
    start, end = local_midnight(frm, tz), local_midnight(to + timedelta(days=1), tz)
    weight = daily(src, hk.METRICS["body_mass"], frm, to, tz)["points"]
    spo2 = daily(src, hk.METRICS["spo2"], frm, to, tz)["points"]
    temp = daily(src, hk.METRICS["body_temp"], frm, to, tz)["points"]
    sys_ = [s for s in src.samples(hk.BP_SYSTOLIC, start, end) if s.start >= start]
    dia = [s for s in src.samples(hk.BP_DIASTOLIC, start, end) if s.start >= start]
    bp = pair_blood_pressure(sys_, dia)
    return {
        "days": [
            {
                "date": w["date"],
                "weight": w["last"],
                "spo2_avg": o["avg"],
                "spo2_min": o["min"],
                "temp": t["avg"],
            }
            for w, o, t in zip(weight, spo2, temp)
        ],
        "blood_pressure": [
            {
                "time": ts.isoformat(),
                "date": local_date(ts, tz).isoformat(),
                "systolic": round(a),
                "diastolic": round(b),
            }
            for ts, a, b in bp
        ],
        "unpaired_bp_readings": len(sys_) + len(dia) - 2 * len(bp),
    }


# ---------------------------------------------------------------- overview


SPARK_DAYS = 30


def _avg(xs: list[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


def summary(src: Source, days: int, tz: ZoneInfo, now: datetime | None = None) -> dict[str, Any]:
    today = today_local(tz, now)
    spark_from = today - timedelta(days=max(SPARK_DAYS, days) - 1)
    avg_from = today - timedelta(days=days)  # the `days` complete days before today
    yesterday = today - timedelta(days=1)

    def window_avg(points: list[dict], key: str) -> float | None:
        return _avg([p[key] for p in points if avg_from.isoformat() <= p["date"] <= yesterday.isoformat()])

    def spark(points: list[dict], key: str) -> list[dict]:
        return [{"date": p["date"], "value": p[key]} for p in points[-SPARK_DAYS:]]

    def latest(points: list[dict], key: str) -> tuple[float | None, str | None]:
        for p in reversed(points):
            if p[key] is not None:
                return p[key], p["date"]
        return None, None

    cards: dict[str, Any] = {}

    for key in ("steps", "active_energy"):
        m = hk.METRICS[key]
        pts = daily(src, m, spark_from, today, tz)["points"]
        cards[key] = {
            "label": "Steps" if key == "steps" else "Active energy",
            "unit": m.display_unit,
            "today": pts[-1]["value"],
            "average": _r(window_avg(pts, "value"), 0),
            "approximate": True,
            "spark": spark(pts, "value"),
        }

    for key in ("resting_hr", "hrv"):
        m = hk.METRICS[key]
        pts = daily(src, m, spark_from, today, tz)["points"]
        val, d = latest(pts, "avg")
        cards[key] = {
            "label": "Resting heart rate" if key == "resting_hr" else "HRV",
            "unit": m.display_unit,
            "latest": val,
            "latest_date": d,
            "average": _r(window_avg(pts, "avg")),
            "spark": spark(pts, "avg"),
        }

    nights = sleep(src, spark_from, today, tz)["nights"]
    last = next((n for n in reversed(nights) if n["has_data"]), None)
    cards["sleep"] = {
        "label": "Sleep",
        "unit": "min",
        "last_night": last,
        "average": _r(
            _avg(
                [
                    n["asleep_min"]
                    for n in nights
                    if n["has_data"] and avg_from.isoformat() < n["night"] <= today.isoformat()
                ]
            )
        ),
        "spark": [
            {"date": n["night"], "value": n["asleep_min"] if n["has_data"] else None}
            for n in nights[-SPARK_DAYS:]
        ],
    }

    m = hk.METRICS["body_mass"]
    pts = daily(src, m, spark_from, today, tz)["points"]
    latest_w = src.latest(m.hk_type)
    cards["weight"] = {
        "label": "Weight",
        "unit": m.display_unit,
        "latest": _r(latest_w.value) if latest_w else None,
        "latest_date": local_date(latest_w.start, tz).isoformat() if latest_w else None,
        "average": _r(window_avg(pts, "last")),
        "spark": spark(pts, "last"),
    }

    return {"today": today.isoformat(), "days": days, "cards": cards}
