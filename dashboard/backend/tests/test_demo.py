from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import hktypes as hk
from app.dedupe import daily_cumulative, daily_raw_sum, nightly_sleep
from app.demo import generate

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def data():
    return generate(now=NOW, tz=LA)


def test_deterministic():
    a = generate(now=NOW, tz=LA, days=20)
    b = generate(now=NOW, tz=LA, days=20)
    assert a == b
    assert generate(now=NOW, tz=LA, days=20, seed=1) != a


def test_covers_every_type(data):
    assert set(data) == hk.ALL_HK_TYPES


def test_covers_about_a_year_and_nothing_in_the_future(data):
    for t, rows in data.items():
        assert rows == sorted(rows, key=lambda s: s.start)
        assert all(s.end <= NOW and s.end >= s.start for s in rows), t
    steps = data[hk.STEPS]
    assert (NOW - steps[0].start).days >= 365


def test_values_are_plausible(data):
    def vals(t):
        return [s.value for s in data[t]]

    assert all(30 <= v <= 200 for v in vals(hk.HEART_RATE))
    assert all(0.85 <= v <= 1.0 for v in vals(hk.SPO2))  # stored as a fraction
    assert all(70 <= v <= 90 for v in vals(hk.BODY_MASS))
    assert all(35 <= v <= 38.5 for v in vals(hk.BODY_TEMP))
    assert {int(v) for v in vals(hk.SLEEP)} <= {0, 1, 2, 3, 4, 5}
    assert all("activity_type" in s.metadata for s in data[hk.WORKOUT])


def test_has_overlapping_sources_that_dedupe_reduces(data):
    days = daily_cumulative(data[hk.STEPS], LA)
    raw = daily_raw_sum(data[hk.STEPS], LA)
    recent = [d for d in days if d >= date(2026, 10, 1)]
    inflated = [d for d in recent if raw[d] > days[d] * 1.2]
    assert len(inflated) > len(recent) / 2, "demo should exercise double counting"
    avg = sum(days[d] for d in recent) / len(recent)
    assert 5000 < avg < 16000


def test_sleep_has_phone_and_watch_overlap(data):
    nights = nightly_sleep(data[hk.SLEEP], LA)
    assert len(nights) > 360
    staged = [n for n in nights if n.deep_s > 0]
    assert len(staged) > 300
    assert any(n.deep_s == 0 and n.asleep_s > 0 for n in nights)  # some phone-only nights
    for n in nights:
        assert n.asleep_s + n.awake_s <= n.in_bed_s + 1e-6
        assert 3 * 3600 < n.in_bed_s < 11 * 3600


def test_some_blood_pressure_is_unpaired(data):
    sys_ = {s.start for s in data[hk.BP_SYSTOLIC]}
    dia = {s.start for s in data[hk.BP_DIASTOLIC]}
    assert dia <= sys_ and len(sys_ - dia) >= 1
