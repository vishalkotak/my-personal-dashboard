from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import hktypes as hk
from app.dedupe import (
    Sample,
    daily_cumulative,
    daily_discrete,
    daily_raw_sum,
    local_midnights,
    night_of,
    nightly_sleep,
    pair_blood_pressure,
    sleep_segments,
)

LA = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc


def la(y, m, d, hh=0, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=LA).astimezone(UTC)


def s(start, minutes, value, **meta):
    return Sample(start, start + timedelta(minutes=minutes), value, meta)


# ---------------------------------------------------------------- cumulative


class TestCumulative:
    def test_single_source_equals_plain_sum(self):
        t = la(2026, 3, 1, 9)
        samples = [s(t, 10, 1000), s(t + timedelta(minutes=10), 5, 400), s(t + timedelta(hours=3), 20, 2100)]
        assert daily_cumulative(samples, LA) == pytest.approx({date(2026, 3, 1): 3500})

    def test_identical_duplicates_are_counted_once(self):
        t = la(2026, 3, 1, 9)
        assert daily_cumulative([s(t, 10, 1000), s(t, 10, 1000)], LA) == pytest.approx(
            {date(2026, 3, 1): 1000}
        )

    def test_phone_and_watch_overlap_takes_the_larger_source(self):
        # Phone: one 10-minute sample of 900. Watch: ten 1-minute samples of 100 = 1000.
        t = la(2026, 3, 1, 9)
        phone = [s(t, 10, 900)]
        watch = [s(t + timedelta(minutes=i), 1, 100) for i in range(10)]
        got = daily_cumulative(phone + watch, LA)[date(2026, 3, 1)]
        assert got == pytest.approx(1000)
        assert daily_raw_sum(phone + watch, LA)[date(2026, 3, 1)] == 1900  # what SUM would say

    def test_partial_overlap_counts_union_with_max_rate(self):
        t = la(2026, 3, 1, 9)
        a = s(t, 10, 100)                          # 10/min over 9:00-9:10
        b = s(t + timedelta(minutes=5), 10, 300)   # 30/min over 9:05-9:15
        # 9:00-9:05 -> a only: 50; 9:05-9:15 -> b wins: 300
        assert daily_cumulative([a, b], LA)[date(2026, 3, 1)] == pytest.approx(350)

    def test_never_more_than_raw_sum_never_less_than_largest_sample(self):
        t = la(2026, 3, 1, 9)
        samples = [s(t + timedelta(minutes=i * 3), 7, 50 + i * 13) for i in range(40)]
        got = daily_cumulative(samples, LA)[date(2026, 3, 1)]
        assert max(x.value for x in samples) <= got <= sum(x.value for x in samples)

    def test_sample_across_local_midnight_is_split_proportionally(self):
        start = la(2026, 3, 1, 23, 50)
        got = daily_cumulative([s(start, 20, 200)], LA)
        assert got == pytest.approx({date(2026, 3, 1): 100, date(2026, 3, 2): 100})

    def test_zero_length_samples(self):
        t = la(2026, 3, 1, 9)
        covered = Sample(t + timedelta(minutes=5), t + timedelta(minutes=5), 77)
        alone = Sample(t + timedelta(hours=2), t + timedelta(hours=2), 33)
        dup = Sample(t + timedelta(hours=2), t + timedelta(hours=2), 33)
        got = daily_cumulative([s(t, 10, 100), covered, alone, dup], LA)
        assert got[date(2026, 3, 1)] == pytest.approx(133)

    def test_empty_and_zero_values(self):
        assert daily_cumulative([], LA) == {}
        assert daily_cumulative([s(la(2026, 3, 1, 9), 10, 0)], LA) == {}

    def test_dst_day_has_23_hours_and_buckets_correctly(self):
        # 2026-03-08 is the spring-forward day in Los Angeles.
        start = la(2026, 3, 7, 23)
        hours = 26  # real hours: 23:00 Mar 7 -> 02:00 Mar 9 local, across a 23-hour day
        sample = Sample(start, start + timedelta(hours=hours), hours * 60)
        got = daily_cumulative([sample], LA)
        assert got[date(2026, 3, 7)] == pytest.approx(60)
        assert got[date(2026, 3, 8)] == pytest.approx(23 * 60)
        assert sum(got.values()) == pytest.approx(hours * 60)

    def test_local_midnights(self):
        ms = local_midnights(la(2026, 3, 1, 12), la(2026, 3, 3, 12), LA)
        assert ms == [la(2026, 3, 2), la(2026, 3, 3)]


# ---------------------------------------------------------------- sleep


class TestSleep:
    def test_night_of_uses_noon_to_noon_window(self):
        assert night_of(la(2026, 3, 2, 7), LA) == date(2026, 3, 2)       # woke up this morning
        assert night_of(la(2026, 3, 1, 23, 30), LA) == date(2026, 3, 2)  # late evening -> tonight
        assert night_of(la(2026, 3, 2, 11, 59), LA) == date(2026, 3, 2)
        assert night_of(la(2026, 3, 2, 12, 0), LA) == date(2026, 3, 3)   # window is half-open
        assert night_of(la(2026, 3, 1, 12, 0), LA) == date(2026, 3, 2)

    def test_staged_watch_data_beats_phone_in_bed(self):
        bed = la(2026, 3, 1, 22, 50)
        phone = [s(bed, 8 * 60 + 20, hk.SLEEP_IN_BED), s(bed + timedelta(minutes=15), 7 * 60, hk.SLEEP_UNSPECIFIED)]
        t = la(2026, 3, 1, 23)
        watch = [
            s(t, 120, hk.SLEEP_CORE),
            s(t + timedelta(minutes=120), 60, hk.SLEEP_DEEP),
            s(t + timedelta(minutes=180), 10, hk.SLEEP_AWAKE),
            s(t + timedelta(minutes=190), 230, hk.SLEEP_REM),
        ]  # 23:00 -> 06:00
        [n] = nightly_sleep(phone + watch, LA)
        assert n.night == date(2026, 3, 2)
        assert n.deep_s == 60 * 60
        assert n.rem_s == 230 * 60
        assert n.awake_s == 10 * 60  # watch's awake wins over phone's "asleep"
        # Phone "asleep" only shows through where the watch has nothing (06:00-06:05).
        assert n.unspecified_s == 5 * 60
        assert n.core_s == 120 * 60
        assert n.asleep_s == n.deep_s + n.core_s + n.rem_s + n.unspecified_s
        assert n.in_bed_s == (8 * 60 + 20) * 60  # union of everything
        assert n.start == bed and n.end == bed + timedelta(minutes=8 * 60 + 20)

    def test_phone_only_night(self):
        bed = la(2026, 3, 1, 23)
        [n] = nightly_sleep([s(bed, 480, hk.SLEEP_IN_BED), s(bed + timedelta(minutes=20), 420, hk.SLEEP_UNSPECIFIED)], LA)
        assert n.asleep_s == 420 * 60 and n.in_bed_s == 480 * 60
        assert n.deep_s == n.rem_s == n.core_s == 0

    def test_duplicate_watch_samples_are_not_double_counted(self):
        t = la(2026, 3, 1, 23)
        a = [s(t, 90, hk.SLEEP_CORE), s(t + timedelta(minutes=90), 30, hk.SLEEP_DEEP)]
        [n] = nightly_sleep(a + list(a), LA)
        assert n.asleep_s == 120 * 60

    def test_segments_merge_adjacent_same_stage(self):
        t = la(2026, 3, 1, 23)
        segs = sleep_segments([s(t, 30, hk.SLEEP_CORE), s(t + timedelta(minutes=30), 30, hk.SLEEP_CORE)])
        assert segs == [(t, t + timedelta(minutes=60), hk.SLEEP_CORE)]

    def test_two_nights_and_a_nap(self):
        n1 = s(la(2026, 3, 1, 23), 420, hk.SLEEP_CORE)
        nap = s(la(2026, 3, 2, 15), 30, hk.SLEEP_CORE)  # afternoon nap ends after noon -> next night
        n2 = s(la(2026, 3, 2, 23), 400, hk.SLEEP_CORE)
        nights = nightly_sleep([n2, nap, n1], LA)
        assert [n.night for n in nights] == [date(2026, 3, 2), date(2026, 3, 3)]
        assert nights[1].asleep_s == 430 * 60

    def test_ignores_unknown_values_and_zero_length(self):
        t = la(2026, 3, 1, 23)
        assert nightly_sleep([s(t, 60, 9), Sample(t, t, hk.SLEEP_CORE)], LA) == []


# ---------------------------------------------------------------- discrete & BP


def test_daily_discrete_avg_min_max_last():
    t = la(2026, 3, 1, 8)
    rows = [s(t, 0, 60), s(t + timedelta(hours=1), 0, 80), s(t + timedelta(hours=2), 0, 70), s(la(2026, 3, 2, 1), 0, 50)]
    [d1, d2] = daily_discrete(rows, LA)
    assert (d1.day, d1.avg, d1.min, d1.max, d1.count, d1.last) == (date(2026, 3, 1), 70, 60, 80, 3, 70)
    assert (d2.day, d2.count) == (date(2026, 3, 2), 1)


def test_daily_discrete_buckets_by_local_not_utc_day():
    # 20:00 local on Mar 1 is 04:00 UTC on Mar 2.
    [d] = daily_discrete([s(la(2026, 3, 1, 20), 0, 55)], LA)
    assert d.day == date(2026, 3, 1)


def test_blood_pressure_pairs_only_identical_start():
    t = la(2026, 3, 1, 9)
    sys_ = [s(t, 0, 120), s(t + timedelta(hours=1), 0, 130)]
    dia = [s(t, 0, 80), s(t + timedelta(hours=1, seconds=1), 0, 85)]
    assert pair_blood_pressure(sys_, dia) == [(t, 120, 80)]
