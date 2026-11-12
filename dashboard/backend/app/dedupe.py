"""Pure functions that turn raw HealthKit samples into honest daily numbers.

Nothing in here touches the database or the network, so it is easy to unit-test.

Why this exists
---------------
The iPhone app uploads *every* raw sample from *every* source (the iPhone itself and the
Apple Watch) but not which source each sample came from. When you walk with both, each
device records the same steps, so a plain ``SUM(value)`` counts them twice. Apple's Health
app avoids this by picking one source per moment according to a priority list. We can't
do that without the source, so we approximate it:

Cumulative types (steps, distance, active energy) -- "max rate per moment"
    Split time into elementary slices at every sample boundary (and at local midnight).
    Within a slice, every sample that covers it is assumed to be spread evenly over its own
    duration, giving a rate (value per second). Instead of adding the rates of overlapping
    samples, we take the **largest** one: overlapping samples are treated as two devices
    describing the same activity, and we believe the one that saw more of it. Samples that
    don't overlap anything are counted in full, exactly as a plain sum would.

    This never double-counts, and for a single device it equals the plain sum. It can
    over-count slightly compared with Apple (it takes the max rather than a fixed priority)
    and it assumes samples are uniform within their interval. That's why the UI labels
    these totals as approximate. The proper fix is for the app to upload the sample's
    ``sourceRevision.source.bundleIdentifier`` so we can pick one source like Apple does.

Sleep -- "most specific stage wins"
    Same slicing idea. When samples overlap, the slice gets the most specific label:
    deep > REM > core > awake > asleep (unspecified) > in bed. The Watch's staged data
    therefore wins over the iPhone's coarse "in bed"/"asleep" blocks, and nothing is
    counted twice. "In bed" for a night is the union of every interval, whatever its label.
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import hktypes as hk


@dataclass(frozen=True)
class Sample:
    start: datetime  # timezone-aware, UTC
    end: datetime
    value: float
    metadata: dict = field(default_factory=dict, compare=False, hash=False)


# ---------------------------------------------------------------- time helpers


def local_midnights(start: datetime, end: datetime, tz: ZoneInfo) -> list[datetime]:
    """UTC instants of every local midnight strictly inside (start, end)."""
    out: list[datetime] = []
    d = start.astimezone(tz).date() + timedelta(days=1)
    last = end.astimezone(tz).date()
    while d <= last:
        m = datetime.combine(d, time(0), tzinfo=tz).astimezone(timezone.utc)
        if start < m < end:
            out.append(m)
        d += timedelta(days=1)
    return out


def local_date(ts: datetime, tz: ZoneInfo) -> date:
    return ts.astimezone(tz).date()


def night_of(end: datetime, tz: ZoneInfo) -> date:
    """The night a sleep interval belongs to.

    A night is named after the morning it ends on and covers local noon-to-noon:
    night D = [D-1 12:00, D 12:00). So anything ending between yesterday noon and
    today noon (bedtime, the night itself, an early nap) is "last night" = today.
    """
    local = end.astimezone(tz)
    # Wall-clock arithmetic on purpose: "noon" means local noon, even across DST changes.
    return (local.replace(tzinfo=None) + timedelta(hours=12)).date()


# ---------------------------------------------------------------- cumulative


def daily_cumulative(samples: list[Sample], tz: ZoneInfo) -> dict[date, float]:
    """Per local day, the de-duplicated total of a cumulative type (see module docstring)."""
    totals: dict[date, float] = defaultdict(float)

    intervals = [s for s in samples if s.end > s.start and s.value > 0]
    points = [s for s in samples if s.end <= s.start and s.value > 0]

    if intervals:
        lo = min(s.start for s in intervals)
        hi = max(s.end for s in intervals)
        cuts = {lo, hi, *local_midnights(lo, hi, tz)}
        for s in intervals:
            cuts.add(s.start)
            cuts.add(s.end)
        bounds = sorted(cuts)

        by_start = sorted(intervals, key=lambda s: s.start)
        active: list[tuple[float, datetime]] = []  # max-heap on rate: (-rate, end)
        i = 0
        for a, b in zip(bounds, bounds[1:]):
            while i < len(by_start) and by_start[i].start <= a:
                s = by_start[i]
                rate = s.value / (s.end - s.start).total_seconds()
                heapq.heappush(active, (-rate, s.end))
                i += 1
            while active and active[0][1] <= a:
                heapq.heappop(active)
            if active:
                totals[local_date(a, tz)] += -active[0][0] * (b - a).total_seconds()

    # Zero-length samples: count them only if no interval sample already covers that
    # instant, and only once per instant (two devices reporting the same moment).
    if points:
        best: dict[datetime, float] = {}
        for p in points:
            best[p.start] = max(best.get(p.start, 0.0), p.value)
        for t, v in best.items():
            if not any(s.start <= t < s.end for s in intervals):
                totals[local_date(t, tz)] += v

    return dict(totals)


def daily_raw_sum(samples: list[Sample], tz: ZoneInfo) -> dict[date, float]:
    """The naive SUM(value) per local day (bucketed by start), for comparison in the UI."""
    totals: dict[date, float] = defaultdict(float)
    for s in samples:
        totals[local_date(s.start, tz)] += s.value
    return dict(totals)


# ---------------------------------------------------------------- sleep

# Higher wins when samples overlap.
SLEEP_PRIORITY = {
    hk.SLEEP_DEEP: 6,
    hk.SLEEP_REM: 5,
    hk.SLEEP_CORE: 4,
    hk.SLEEP_AWAKE: 3,
    hk.SLEEP_UNSPECIFIED: 2,
    hk.SLEEP_IN_BED: 1,
}


@dataclass
class Night:
    night: date
    asleep_s: float = 0.0       # deep + core + REM + unspecified
    deep_s: float = 0.0
    core_s: float = 0.0
    rem_s: float = 0.0
    unspecified_s: float = 0.0
    awake_s: float = 0.0
    in_bed_s: float = 0.0       # union of every interval, whatever its label
    start: datetime | None = None
    end: datetime | None = None


def sleep_segments(samples: list[Sample]) -> list[tuple[datetime, datetime, int]]:
    """Flatten overlapping sleep samples into non-overlapping (start, end, stage) pieces."""
    valid = [s for s in samples if s.end > s.start and int(s.value) in SLEEP_PRIORITY]
    if not valid:
        return []
    bounds = sorted({t for s in valid for t in (s.start, s.end)})
    by_start = sorted(valid, key=lambda s: s.start)
    active: list[tuple[int, datetime]] = []  # max-heap on priority: (-priority, end)
    i = 0
    out: list[tuple[datetime, datetime, int]] = []
    for a, b in zip(bounds, bounds[1:]):
        while i < len(by_start) and by_start[i].start <= a:
            s = by_start[i]
            heapq.heappush(active, (-SLEEP_PRIORITY[int(s.value)], s.end))
            i += 1
        while active and active[0][1] <= a:
            heapq.heappop(active)
        if not active:
            continue
        stage = _stage_for_priority(-active[0][0])
        if out and out[-1][1] == a and out[-1][2] == stage:
            out[-1] = (out[-1][0], b, stage)  # extend the previous piece
        else:
            out.append((a, b, stage))
    return out


_PRIORITY_TO_STAGE = {p: s for s, p in SLEEP_PRIORITY.items()}


def _stage_for_priority(p: int) -> int:
    return _PRIORITY_TO_STAGE[p]


def nightly_sleep(samples: list[Sample], tz: ZoneInfo) -> list[Night]:
    nights: dict[date, Night] = {}
    for a, b, stage in sleep_segments(samples):
        key = night_of(b, tz)
        n = nights.setdefault(key, Night(night=key))
        secs = (b - a).total_seconds()
        n.in_bed_s += secs
        if stage == hk.SLEEP_DEEP:
            n.deep_s += secs
        elif stage == hk.SLEEP_REM:
            n.rem_s += secs
        elif stage == hk.SLEEP_CORE:
            n.core_s += secs
        elif stage == hk.SLEEP_UNSPECIFIED:
            n.unspecified_s += secs
        elif stage == hk.SLEEP_AWAKE:
            n.awake_s += secs
        n.start = a if n.start is None else min(n.start, a)
        n.end = b if n.end is None else max(n.end, b)
    for n in nights.values():
        n.asleep_s = n.deep_s + n.core_s + n.rem_s + n.unspecified_s
    return [nights[k] for k in sorted(nights)]


# ---------------------------------------------------------------- discrete


@dataclass
class DayStat:
    day: date
    avg: float
    min: float
    max: float
    count: int
    last: float  # most recent value that day (by start time)


def daily_discrete(samples: list[Sample], tz: ZoneInfo) -> list[DayStat]:
    """avg/min/max/count per local day, bucketed by start. Mirrors the SQL version exactly."""
    groups: dict[date, list[Sample]] = defaultdict(list)
    for s in samples:
        groups[local_date(s.start, tz)].append(s)
    out = []
    for d in sorted(groups):
        vals = [s.value for s in groups[d]]
        last = max(groups[d], key=lambda s: s.start).value
        out.append(DayStat(d, sum(vals) / len(vals), min(vals), max(vals), len(vals), last))
    return out


def pair_blood_pressure(
    systolic: list[Sample], diastolic: list[Sample]
) -> list[tuple[datetime, float, float]]:
    """Match systolic and diastolic readings that share an identical start time."""
    dia = {s.start: s.value for s in diastolic}
    return sorted((s.start, s.value, dia[s.start]) for s in systolic if s.start in dia)
