"""SQL builders. Every query is a constant string with named placeholders; user input only
ever travels as a bound parameter, never as part of the SQL text.

They're plain functions returning (sql, params) so they can be tested without a database.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from . import hktypes as hk

Query = tuple[str, dict[str, Any]]

# Samples can start before the window and still overlap it (a long sleep block, a
# 10-minute step sample). Bounding start_date as well keeps the index range tight.
MAX_SAMPLE_LOOKBACK = timedelta(days=2)


def _user_clause(user_id: str | None, params: dict[str, Any]) -> str:
    if user_id is None:
        return ""
    params["user_id"] = user_id
    return " and user_id = %(user_id)s"


def _check_type(hk_type: str) -> None:
    if hk_type not in hk.ALL_HK_TYPES:  # defence in depth; the API validates first
        raise ValueError(f"unknown type {hk_type!r}")


def samples_query(hk_type: str, start: datetime, end: datetime, user_id: str | None) -> Query:
    """Raw samples that overlap [start, end)."""
    _check_type(hk_type)
    params: dict[str, Any] = {
        "type": hk_type,
        "start": start,
        "end": end,
        "lookback": start - MAX_SAMPLE_LOOKBACK,
    }
    sql = (
        "select start_date, end_date, value, metadata"
        " from public.health_samples"
        " where type = %(type)s"
        " and start_date >= %(lookback)s and start_date < %(end)s"
        " and end_date > %(start)s"
        + _user_clause(user_id, params)
        + " order by start_date"
    )
    return sql, params


def daily_stats_query(
    hk_type: str, start: datetime, end: datetime, tz_name: str, user_id: str | None
) -> Query:
    """avg/min/max/count/last per local day for a discrete type, bucketed by start_date."""
    _check_type(hk_type)
    params: dict[str, Any] = {"type": hk_type, "start": start, "end": end, "tz": tz_name}
    sql = (
        "select (date_trunc('day', start_date, %(tz)s) at time zone %(tz)s)::date as day,"
        " avg(value) as avg, min(value) as min, max(value) as max, count(*) as count,"
        " (array_agg(value order by start_date desc))[1] as last"
        " from public.health_samples"
        " where type = %(type)s and start_date >= %(start)s and start_date < %(end)s"
        + _user_clause(user_id, params)
        + " group by 1 order by 1"
    )
    return sql, params


def latest_query(hk_type: str, user_id: str | None) -> Query:
    _check_type(hk_type)
    params: dict[str, Any] = {"type": hk_type}
    sql = (
        "select start_date, end_date, value, metadata"
        " from public.health_samples where type = %(type)s"
        + _user_clause(user_id, params)
        + " order by start_date desc limit 1"
    )
    return sql, params


def last_upload_query(user_id: str | None) -> Query:
    params: dict[str, Any] = {}
    where = _user_clause(user_id, params).replace(" and ", " where ", 1)
    return "select max(uploaded_at) from public.health_samples" + where, params
