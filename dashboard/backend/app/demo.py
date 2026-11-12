"""Synthetic, realistic-looking Apple Health data for demo mode (DEMO=1).

Deterministic: the same seed and the same "now" always give the same data. It
deliberately reproduces the messy parts of real HealthKit exports so the de-duplication
gets exercised:

* steps, distance and active energy are recorded by BOTH a "phone" and a "watch",
  overlapping in time, with different sample granularity;
* sleep has a coarse iPhone "in bed" block (and sometimes "asleep") on top of the
  watch's staged samples, and some nights have no watch at all;
* blood pressure occasionally has a systolic reading without its diastolic partner;
* a few extra types (VO2 max, respiratory rate, water, protein, flights climbed,
  mindful minutes, headaches) so the Explore tab has something to show.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import hktypes as hk
from .dedupe import Sample

VO2MAX = "HKQuantityTypeIdentifierVO2Max"
RESP_RATE = "HKQuantityTypeIdentifierRespiratoryRate"
WATER = "HKQuantityTypeIdentifierDietaryWater"
PROTEIN = "HKQuantityTypeIdentifierDietaryProtein"
FLIGHTS = "HKQuantityTypeIdentifierFlightsClimbed"
MINDFUL = "HKCategoryTypeIdentifierMindfulSession"
HEADACHE = "HKCategoryTypeIdentifierHeadache"

# Stored unit per type, as the iPhone app writes them.
UNITS = {
    **{m.hk_type: m.unit for m in hk.METRICS.values()},
    hk.SLEEP: "category",
    hk.WORKOUT: "s",
    VO2MAX: "ml/(kg*min)",
    RESP_RATE: "count/min",
    WATER: "mL",
    PROTEIN: "g",
    FLIGHTS: "count",
    MINDFUL: "category",
    HEADACHE: "category",
}

DEFAULT_SEED = 20261111
DAYS = 400

WORKOUT_CHOICES = [  # (activity_type, weight, (min, max) minutes, steps/min, kcal/min, hr)
    (37, 5, (25, 55), 160, 11.0, 150),   # running
    (50, 4, (35, 70), 0, 5.0, 115),      # traditional strength
    (13, 3, (30, 90), 0, 8.5, 135),      # cycling
    (57, 2, (20, 45), 0, 3.0, 95),       # yoga
    (63, 2, (15, 30), 40, 10.0, 155),    # HIIT
    (52, 3, (30, 75), 105, 4.5, 105),    # walking
    (46, 1, (25, 50), 0, 9.0, 130),      # swimming
    (20, 2, (30, 50), 0, 6.0, 120),      # functional strength
    (99, 1, (20, 40), 0, 5.0, 110),      # something unmapped -> "Other"
]


def _utc(d: date, hour: float, tz: ZoneInfo) -> datetime:
    """Local date + fractional hour -> UTC instant. Hours >= 24 roll into the next day."""
    base = datetime.combine(d, time(0), tzinfo=tz)
    return (base + timedelta(hours=hour)).astimezone(timezone.utc)


def _chunks(start: datetime, end: datetime, total: float, chunk_min: float, rng: random.Random):
    """Split [start, end) into roughly chunk_min-long pieces sharing `total` (jittered)."""
    secs = (end - start).total_seconds()
    if secs <= 0 or total <= 0:
        return []
    n = max(1, round(secs / (chunk_min * 60)))
    weights = [rng.uniform(0.6, 1.4) for _ in range(n)]
    wsum = sum(weights)
    out, t = [], start
    for i, w in enumerate(weights):
        t2 = end if i == n - 1 else start + timedelta(seconds=secs * (i + 1) / n)
        out.append((t, t2, total * w / wsum))
        t = t2
    return out


def generate(
    now: datetime | None = None,
    tz: ZoneInfo | None = None,
    seed: int = DEFAULT_SEED,
    days: int = DAYS,
) -> dict[str, list[Sample]]:
    tz = tz or ZoneInfo("America/Los_Angeles")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = now.astimezone(tz).date()
    rng = random.Random(f"{seed}:{today.isoformat()}")
    out: dict[str, list[Sample]] = defaultdict(list)

    def add(t: str, start: datetime, end: datetime, value: float, meta: dict | None = None):
        if end <= now:
            out[t].append(Sample(start, end, value, meta or {}))

    weight = 82.4
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        progress = 1 - i / days  # 0 -> 1 across the period: slowly getting fitter
        weekend = d.weekday() >= 5
        resting = 59 - 3.5 * progress + 1.5 * math.sin(i / 9) + rng.gauss(0, 1.0)
        watch_today = rng.random() > 0.05

        # ---------------------------------------------------------------- sleep (ends this morning)
        bedtime = 23.0 + (0.6 if weekend else 0) + rng.gauss(0, 0.6)  # hours after previous midnight
        duration = max(4.5, min(9.5, rng.gauss(7.3 if not weekend else 7.9, 0.8)))
        prev = d - timedelta(days=1)
        sleep_start = _utc(prev, bedtime, tz)
        sleep_end = sleep_start + timedelta(hours=duration)
        sleep_quality = 0.0
        if rng.random() < 0.92:  # the iPhone's coarse "in bed" block
            add(hk.SLEEP, sleep_start - timedelta(minutes=rng.randint(5, 25)),
                sleep_end + timedelta(minutes=rng.randint(2, 15)), hk.SLEEP_IN_BED)
        if rng.random() < 0.3:   # ...sometimes also an unstaged "asleep" block
            add(hk.SLEEP, sleep_start + timedelta(minutes=10), sleep_end, hk.SLEEP_UNSPECIFIED)
        if watch_today and rng.random() > 0.04:
            t = sleep_start
            cycle = 0
            deep_total = 0.0
            while t < sleep_end:
                early = cycle < 2
                stages = [
                    (hk.SLEEP_CORE, rng.uniform(25, 45)),
                    (hk.SLEEP_DEEP, rng.uniform(15, 35) if early else rng.uniform(0, 12)),
                    (hk.SLEEP_CORE, rng.uniform(10, 20)),
                    (hk.SLEEP_REM, rng.uniform(8, 18) if early else rng.uniform(18, 35)),
                ]
                if rng.random() < 0.45:
                    stages.append((hk.SLEEP_AWAKE, rng.uniform(1, 9)))
                for stage, minutes in stages:
                    if minutes < 1 or t >= sleep_end:
                        continue
                    t2 = min(sleep_end, t + timedelta(minutes=minutes))
                    add(hk.SLEEP, t, t2, stage)
                    if stage == hk.SLEEP_DEEP:
                        deep_total += (t2 - t).total_seconds() / 60
                    t = t2
                cycle += 1
            sleep_quality = deep_total / 60
            # Overnight heart rate, SpO2 (fraction 0-1, as HealthKit's percent unit stores it)
            t = sleep_start
            while t < sleep_end:
                add(hk.HEART_RATE, t, t, round(resting + rng.gauss(-2, 2.5)))
                t += timedelta(minutes=15)
            for _ in range(rng.randint(3, 8)):
                ts = sleep_start + timedelta(minutes=rng.uniform(20, duration * 60 - 10))
                add(hk.SPO2, ts, ts, round(min(1.0, rng.gauss(0.965, 0.012)), 3))
            for _ in range(rng.randint(3, 6)):
                ts = sleep_start + timedelta(minutes=rng.uniform(20, duration * 60 - 10))
                add(RESP_RATE, ts, ts, round(rng.gauss(14.5, 0.9), 1))

        # ---------------------------------------------------------------- vitals
        if watch_today:
            ts = _utc(d, 7.5 + rng.random(), tz)
            add(hk.RESTING_HR, ts, ts, round(resting))
            hrv_base = 44 + 8 * progress + 6 * (sleep_quality - 1) - (resting - 57)
            for _ in range(rng.randint(3, 6)):
                ts = _utc(d, rng.uniform(1, 23), tz)
                add(hk.HRV, ts, ts, round(max(12, rng.gauss(hrv_base, 9)), 1))

        if rng.random() < 0.7:
            weight += rng.gauss(-0.008, 0.18)
            weight = min(84.0, max(77.0, weight))
            ts = _utc(d, 7.2 + rng.random() * 0.8, tz)
            add(hk.BODY_MASS, ts, ts, round(weight + rng.gauss(0, 0.25), 1))
        else:
            weight += -0.008

        if rng.random() < 0.28:
            ts = _utc(d, 8 + rng.random() * 12, tz)
            sys_ = round(rng.gauss(119 - 3 * progress, 6))
            add(hk.BP_SYSTOLIC, ts, ts, sys_)
            if rng.random() > 0.05:  # occasionally the partner reading is missing
                add(hk.BP_DIASTOLIC, ts, ts, round(rng.gauss(77 - 2 * progress, 4)))

        if rng.random() < 0.12:
            ts = _utc(d, 8 + rng.random() * 12, tz)
            add(hk.BODY_TEMP, ts, ts, round(rng.gauss(36.7, 0.2), 2))

        # ---------------------------------------------------------------- extras for Explore
        if watch_today and rng.random() < 0.15:
            ts = _utc(d, 18 + rng.random(), tz)
            add(VO2MAX, ts, ts, round(rng.gauss(41.5 + 2.5 * progress, 0.6), 1))
        for _ in range(rng.randint(3, 8)):
            ts = _utc(d, rng.uniform(7.5, 21.5), tz)
            add(WATER, ts, ts, rng.choice([250.0, 330.0, 500.0]))
            if rng.random() < 0.08:  # a second app logging the same glass at the same moment
                add(WATER, ts, ts, 250.0)
        for meal in (8.0, 12.5, 19.0):
            if rng.random() < 0.85:
                ts = _utc(d, meal + rng.uniform(0, 1), tz)
                add(PROTEIN, ts, ts, round(rng.uniform(18, 45), 1))
        if rng.random() < 0.35:
            ts = _utc(d, rng.choice([7.8, 13.0, 21.8]), tz)
            add(MINDFUL, ts, ts + timedelta(minutes=rng.choice([5, 10, 10, 15, 20])), 0)
        if rng.random() < 0.05:
            ts = _utc(d, rng.uniform(10, 18), tz)
            add(HEADACHE, ts, ts + timedelta(hours=rng.uniform(0.5, 4)), rng.choice([2, 2, 3, 4]))

        # ---------------------------------------------------------------- daytime activity
        target = max(1500, rng.gauss(9000 + 1500 * progress - (1500 if weekend else 0), 2600))
        n_bouts = rng.randint(7, 14)
        wake = sleep_end.astimezone(tz)
        wake_h = wake.hour + wake.minute / 60 if wake.date() == d else 7.0
        bouts = []
        for _ in range(n_bouts):
            h = rng.uniform(wake_h + 0.3, 21.5)
            minutes = rng.uniform(4, 35)
            bouts.append((h, minutes))
        total_min = sum(m for _, m in bouts)
        for h, minutes in bouts:
            b_start = _utc(d, h, tz)
            b_end = b_start + timedelta(minutes=minutes)
            steps = target * minutes / total_min
            meters = steps * rng.uniform(0.72, 0.8)
            kcal = minutes * rng.uniform(3.5, 5.0)
            phone_carried = rng.random() < 0.8
            flights = rng.choice([0, 0, 0, 1, 1, 2, 3])
            if watch_today:
                for a, b, v in _chunks(b_start, b_end, steps, 2.5, rng):
                    add(hk.STEPS, a, b, round(v))
                for a, b, v in _chunks(b_start, b_end, meters, 2.5, rng):
                    add(hk.DISTANCE, a, b, round(v, 1))
                for a, b, v in _chunks(b_start, b_end, kcal, 5, rng):
                    add(hk.ACTIVE_ENERGY, a, b, round(v, 2))
                if flights:
                    add(FLIGHTS, b_start, b_end, flights)
            if phone_carried or not watch_today:
                seen = rng.uniform(0.85, 1.0)  # the phone misses a little when it's on a desk
                for a, b, v in _chunks(b_start, b_end, steps * seen, 8, rng):
                    add(hk.STEPS, a, b, round(v))
                for a, b, v in _chunks(b_start, b_end, meters * seen, 8, rng):
                    add(hk.DISTANCE, a, b, round(v, 1))
                if flights:
                    add(FLIGHTS, b_start, b_end, flights)
                if rng.random() < 0.5:
                    for a, b, v in _chunks(b_start, b_end, kcal * 0.6, 10, rng):
                        add(hk.ACTIVE_ENERGY, a, b, round(v, 2))

        if watch_today:
            # Low-level background active energy and heart rate across the waking day.
            day_start, day_end = _utc(d, wake_h + 0.2, tz), _utc(d, 22.8, tz)
            for a, b, v in _chunks(day_start, day_end, rng.uniform(90, 220), 15, rng):
                add(hk.ACTIVE_ENERGY, a, b, round(v, 2))
            t = day_start
            while t < day_end:
                add(hk.HEART_RATE, t, t, round(resting + 14 + rng.gauss(0, 8)))
                t += timedelta(minutes=10)

        # ---------------------------------------------------------------- workouts
        if rng.random() < (0.45 if weekend else 0.55):
            choice = rng.choices(WORKOUT_CHOICES, weights=[c[1] for c in WORKOUT_CHOICES])[0]
            activity, _, (lo, hi), spm, kpm, hr = choice
            minutes = rng.uniform(lo, hi)
            w_start = _utc(d, rng.choice([6.5, 7.0, 12.2, 17.5, 18.3]) + rng.random() * 0.5, tz)
            w_end = w_start + timedelta(minutes=minutes)
            add(hk.WORKOUT, w_start, w_end, round(minutes * 60), {"activity_type": str(activity)})
            for a, b, v in _chunks(w_start, w_end, kpm * minutes, 5, rng):
                add(hk.ACTIVE_ENERGY, a, b, round(v, 2))
            if spm:
                for a, b, v in _chunks(w_start, w_end, spm * minutes, 2.5, rng):
                    add(hk.STEPS, a, b, round(v))
                    add(hk.DISTANCE, a, b, round(v * 0.9, 1))
            t = w_start
            while t < w_end:
                add(hk.HEART_RATE, t, t, round(hr + rng.gauss(0, 9) - 2 * progress))
                t += timedelta(minutes=2)

    return {t: sorted(v, key=lambda s: s.start) for t, v in out.items()}
