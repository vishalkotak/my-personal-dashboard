"""Where samples come from: the real Supabase database, or the synthetic demo data.

Both implement the same small interface, and everything above this layer (the
aggregation in service.py, the API) is shared, so demo mode exercises the same code
paths as real data.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from . import queries
from .config import Settings
from .dedupe import DayStat, Sample, daily_discrete

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TypeStat:
    type: str
    unit: str
    count: int
    latest: datetime | None


class Source(Protocol):
    def samples(self, hk_type: str, start: datetime, end: datetime) -> list[Sample]: ...
    def daily_stats(self, hk_type: str, start: datetime, end: datetime) -> list[DayStat]: ...
    def latest(self, hk_type: str) -> Sample | None: ...
    def last_upload(self) -> datetime | None: ...
    def type_stats(self) -> list[TypeStat]: ...
    def ping(self) -> bool: ...
    def close(self) -> None: ...


class PostgresSource:
    """Read-only access to public.health_samples through a small connection pool."""

    def __init__(self, settings: Settings):
        from psycopg_pool import ConnectionPool

        if not settings.database_url:
            raise SystemExit(
                "DATABASE_URL is not set. Copy dashboard/.env.example to dashboard/.env "
                "and fill it in, or run with DEMO=1."
            )
        self.settings = settings
        timeout = int(settings.statement_timeout_ms)

        def configure(conn) -> None:
            # Belt and braces: the database role is already read-only with a timeout
            # (see sql/readonly_role.sql), but enforce it on every connection too.
            conn.autocommit = True
            conn.execute("set default_transaction_read_only = on")
            conn.execute("select set_config('statement_timeout', %s, false)", (str(timeout),))
            conn.execute("set idle_in_transaction_session_timeout = 30000")
            conn.execute("set time zone 'UTC'")

        self.pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=4,
            timeout=10,
            open=False,
            configure=configure,
            # Prepared statements don't mix well with Supabase's pooler.
            kwargs={"prepare_threshold": None, "connect_timeout": 10},
            name="healthsync-dashboard",
        )
        # Don't block start-up if the database is unreachable; /api/health will say so.
        self.pool.open(wait=False)
        self._user_id = settings.user_id
        self._user_resolved = settings.user_id is not None
        self._user_lock = threading.Lock()

    @property
    def user_id(self) -> str | None:
        """HEALTH_USER_ID, or the only account in the table when it's unset.

        The table's index starts with user_id, so filtering on it turns ~1 s scans into
        ~10 ms index lookups. With a single account there's nothing to choose, so detect it.
        """
        if self._user_resolved:
            return self._user_id
        with self._user_lock:
            if not self._user_resolved:
                ids = [r[0] for r in self._fetch(queries.distinct_users_query())]
                if len(ids) == 1:
                    self._user_id = str(ids[0])
                    log.info("one account in the table; filtering on it so queries use the index")
                elif ids:
                    log.warning(
                        "%d accounts in the table and HEALTH_USER_ID is unset: showing all of them, "
                        "and queries will be slow. Set HEALTH_USER_ID in dashboard/.env.", len(ids)
                    )
                self._user_resolved = True
        return self._user_id

    def _fetch(self, q: queries.Query) -> list[tuple]:
        sql, params = q
        with self.pool.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def samples(self, hk_type, start, end):
        rows = self._fetch(queries.samples_query(hk_type, start, end, self.user_id))
        return [Sample(r[0], r[1], float(r[2]), r[3] or {}) for r in rows]

    def daily_stats(self, hk_type, start, end):
        q = queries.daily_stats_query(
            hk_type, start, end, self.settings.tz_name, self.user_id
        )
        return [
            DayStat(r[0], float(r[1]), float(r[2]), float(r[3]), int(r[4]), float(r[5]))
            for r in self._fetch(q)
        ]

    def latest(self, hk_type):
        rows = self._fetch(queries.latest_query(hk_type, self.user_id))
        if not rows:
            return None
        r = rows[0]
        return Sample(r[0], r[1], float(r[2]), r[3] or {})

    def last_upload(self):
        rows = self._fetch(queries.last_upload_query(self.user_id))
        return rows[0][0] if rows else None

    def type_stats(self):
        rows = self._fetch(queries.type_stats_query(self.user_id))
        return [TypeStat(r[0], r[1], int(r[2]), r[3]) for r in rows]

    def ping(self) -> bool:
        try:
            with self.pool.connection(timeout=5) as conn:
                conn.execute("select 1")
            return True
        except Exception as e:  # noqa: BLE001 - report, never crash the health check
            log.warning("database ping failed: %s", type(e).__name__)
            return False

    def close(self) -> None:
        self.pool.close()


class MemorySource:
    """Serves samples from memory. Used for demo mode and in tests."""

    def __init__(
        self,
        by_type: dict[str, list[Sample]],
        settings: Settings,
        last_upload=None,
        units: dict[str, str] | None = None,
    ):
        self.settings = settings
        self.units = units or {}
        self.by_type = {t: sorted(v, key=lambda s: s.start) for t, v in by_type.items()}
        self._last_upload = last_upload

    def samples(self, hk_type, start, end):
        lookback = start - queries.MAX_SAMPLE_LOOKBACK
        return [
            s
            for s in self.by_type.get(hk_type, [])
            if lookback <= s.start < end and s.end > start
        ]

    def daily_stats(self, hk_type, start, end):
        rows = [s for s in self.by_type.get(hk_type, []) if start <= s.start < end]
        return daily_discrete(rows, self.settings.tz)

    def latest(self, hk_type):
        rows = self.by_type.get(hk_type)
        return rows[-1] if rows else None

    def last_upload(self):
        return self._last_upload

    def type_stats(self):
        return [
            TypeStat(t, self.units.get(t, ""), len(rows), max(s.end for s in rows))
            for t, rows in sorted(self.by_type.items())
            if rows
        ]

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        pass
