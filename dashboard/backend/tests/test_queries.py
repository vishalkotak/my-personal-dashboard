from datetime import datetime, timezone

import pytest

from app import hktypes as hk
from app import queries

T0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
T1 = datetime(2026, 3, 8, tzinfo=timezone.utc)
UID = "6f1c2a3e-0000-4000-8000-000000000001"


def all_queries(user_id):
    return [
        queries.samples_query(hk.STEPS, T0, T1, user_id),
        queries.daily_stats_query(hk.HEART_RATE, T0, T1, "America/Los_Angeles", user_id),
        queries.latest_query(hk.BODY_MASS, user_id),
        queries.last_upload_query(user_id),
    ]


@pytest.mark.parametrize("user_id", [None, UID])
def test_queries_are_select_only_and_parameterized(user_id):
    for sql, params in all_queries(user_id):
        low = sql.lower()
        assert low.startswith("select ")
        for word in ("insert", "update", "delete", "drop", "alter", "grant", "truncate", ";"):
            assert word not in low
        # every value travels as a bound parameter, never inside the SQL text
        for v in params.values():
            assert str(v) not in sql
        for name in params:
            assert f"%({name})s" in sql


def test_user_filter_only_when_configured():
    sql, params = queries.samples_query(hk.STEPS, T0, T1, None)
    assert "user_id" not in sql and "user_id" not in params
    sql, params = queries.samples_query(hk.STEPS, T0, T1, UID)
    assert "user_id = %(user_id)s" in sql and params["user_id"] == UID
    sql, _ = queries.last_upload_query(UID)
    assert sql.endswith(" where user_id = %(user_id)s")


def test_samples_query_includes_lookback_for_overlaps():
    _, params = queries.samples_query(hk.SLEEP, T0, T1, None)
    assert params["lookback"] == T0 - queries.MAX_SAMPLE_LOOKBACK


def test_daily_stats_buckets_in_configured_tz():
    sql, params = queries.daily_stats_query(hk.HRV, T0, T1, "Europe/London", None)
    assert "date_trunc('day', start_date, %(tz)s)" in sql and params["tz"] == "Europe/London"


@pytest.mark.parametrize("bad", ["x", "steps", "HKQuantityTypeIdentifierDietaryCaffeine", "'; drop table x; --"])
def test_builders_reject_types_outside_allowlist(bad):
    with pytest.raises(ValueError):
        queries.samples_query(bad, T0, T1, None)
    with pytest.raises(ValueError):
        queries.daily_stats_query(bad, T0, T1, "UTC", None)
