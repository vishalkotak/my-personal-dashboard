"""SQL builders. Every query is a constant string with named placeholders; user input only
ever travels as a bound parameter, never as part of the SQL text.

They're plain functions returning (sql, params) so they can be tested without a database.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

Query = tuple[str, dict[str, Any]]

# Samples can start before the window and still overlap it (a long sleep block, a
# 10-minute step sample). Bounding start_date as well keeps the index range tight.
MAX_SAMPLE_LOOKBACK = timedelta(days=2)


def _user_clause(user_id: str | None, params: dict[str, Any]) -> str:
    if user_id is None:
        return ""
    params["user_id"] = user_id
    return " and user_id = %(user_id)s"


_TYPE_RE = re.compile(r"HK[A-Za-z0-9]{1,126}")


def _check_type(hk_type: str) -> None:
    # Defence in depth: the API already checks the type against the catalog, and the
    # value is a bound parameter anyway. This just refuses anything that isn't shaped
    # like a HealthKit identifier.
    if not isinstance(hk_type, str) or not _TYPE_RE.fullmatch(hk_type):
        raise ValueError(f"invalid type {hk_type!r}")


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


def type_stats_query(user_id: str | None) -> Query:
    """Which types have data: row count and latest sample per type."""
    params: dict[str, Any] = {}
    where = _user_clause(user_id, params).replace(" and ", " where ", 1)
    return (
        "select type, min(unit) as unit, count(*) as n, max(end_date) as latest"
        " from public.health_samples" + where + " group by type order by type",
        params,
    )


def last_upload_query(user_id: str | None) -> Query:
    params: dict[str, Any] = {}
    where = _user_clause(user_id, params).replace(" and ", " where ", 1)
    return "select max(uploaded_at) from public.health_samples" + where, params


def distinct_users_query() -> Query:
    """Up to 3 distinct account IDs, found by hopping along the (user_id, ...) index.

    A plain `select distinct user_id` reads the whole table; this touches a few index pages.
    """
    return (
        "with recursive u as ("
        " (select user_id from public.health_samples order by user_id limit 1)"
        " union all"
        " select (select h.user_id from public.health_samples h"
        "  where h.user_id > u.user_id order by h.user_id limit 1)"
        " from u where u.user_id is not null)"
        " select user_id from u where user_id is not null limit 3",
        {},
    )
