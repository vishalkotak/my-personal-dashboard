"""Integration tests against a real Postgres.

Skipped unless TEST_DATABASE_ADMIN_URL points at a throwaway Postgres superuser
connection. `scripts/integration-test.sh` starts one in Docker and runs these.

What they prove:
  * apple-health-sync/supabase/schema.sql and dashboard/sql/readonly_role.sql run on a
    Supabase-like setup where the owner is NOT a superuser (like Supabase's `postgres`);
  * the reader role can SELECT health_samples and nothing else, and can't write at all;
  * the SQL aggregation gives exactly the same answers as the in-memory (demo) path.
"""

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import errors  # noqa: E402

from app import hktypes as hk  # noqa: E402
from app import service  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.demo import generate  # noqa: E402
from app.sources import MemorySource, PostgresSource  # noqa: E402

ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="TEST_DATABASE_ADMIN_URL not set")

REPO = Path(__file__).resolve().parents[3]
SCHEMA_SQL = REPO / "apple-health-sync" / "supabase" / "schema.sql"
READER_SQL = REPO / "dashboard" / "sql" / "readonly_role.sql"
TZ = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)
OWNER_PW = "owner-test-password-not-secret"
READER_PW = "reader-test-password-not-secret-0123456789"
ME = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER = uuid.UUID("22222222-2222-4222-8222-222222222222")


def with_user(url: str, user: str, pw: str) -> str:
    p = urlsplit(url)
    host = p.hostname + (f":{p.port}" if p.port else "")
    return urlunsplit((p.scheme, f"{user}:{pw}@{host}", p.path, p.query, p.fragment))


@pytest.fixture(scope="module")
def db():
    """Fresh database emulating Supabase: auth schema stub, non-superuser owner."""
    name = "hs_test_" + uuid.uuid4().hex[:8]
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
        for role in ("healthsync_reader", "supa_owner"):
            admin.execute(f"drop role if exists {role}")
    db_admin_url = urlunsplit(urlsplit(ADMIN_URL)._replace(path=f"/{name}"))
    with psycopg.connect(db_admin_url, autocommit=True) as c:
        c.execute(
            f"""
            do $$ begin
              if not exists (select from pg_roles where rolname='anon') then create role anon nologin; end if;
              if not exists (select from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
            end $$;
            create role supa_owner login createrole password '{OWNER_PW}';
            create schema auth;
            create table auth.users (id uuid primary key);
            create function auth.uid() returns uuid language sql stable
              as $f$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $f$;
            grant usage on schema auth to supa_owner, authenticated;
            grant select, references on auth.users to supa_owner;
            grant create, usage on schema public to supa_owner;
            insert into auth.users values ('{ME}'), ('{OTHER}');
            """
        )
    owner_url = with_user(db_admin_url, "supa_owner", OWNER_PW)
    with psycopg.connect(owner_url, autocommit=True) as c:
        c.execute(SCHEMA_SQL.read_text())
        c.execute(READER_SQL.read_text().replace("REPLACE_WITH_A_STRONG_PASSWORD", READER_PW))
    yield {"admin": db_admin_url, "owner": owner_url, "reader": with_user(db_admin_url, "healthsync_reader", READER_PW)}
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'drop database "{name}" with (force)')
        admin.execute("drop role if exists healthsync_reader")
        admin.execute("drop role if exists supa_owner")


@pytest.fixture(scope="module")
def seeded(db):
    data = generate(now=NOW, tz=TZ, days=60)
    rows = []
    for t, samples in data.items():
        for s in samples:
            rows.append((ME, uuid.uuid4(), t, s.start, s.end, s.value, hk_unit(t), json.dumps(s.metadata)))
    # Another account's rows: the reader sees them (by design), HEALTH_USER_ID filters them.
    rows.append((OTHER, uuid.uuid4(), hk.BODY_MASS, NOW, NOW, 55.0, "kg", "{}"))
    with psycopg.connect(db["admin"]) as c:
        with c.cursor() as cur:
            cur.executemany(
                "insert into public.health_samples (user_id, hk_uuid, type, start_date, end_date, value, unit, metadata)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                rows,
            )
    return data, len(rows)


def hk_unit(t: str) -> str:
    m = hk.lookup_metric(t)
    return m.unit if m else ("s" if t == hk.WORKOUT else "category")


# ---------------------------------------------------------------- role & permissions


def test_reader_session_is_read_only_with_timeout(db):
    with psycopg.connect(db["reader"]) as c:
        assert c.execute("show default_transaction_read_only").fetchone()[0] == "on"
        assert c.execute("show statement_timeout").fetchone()[0] == "15s"
        attrs = c.execute(
            "select rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls"
            " from pg_roles where rolname = current_user"
        ).fetchone()
        assert attrs == (False, False, False, False, False)


def test_reader_can_select_all_rows(db, seeded):
    _, n = seeded
    with psycopg.connect(db["reader"]) as c:
        assert c.execute("select count(*) from public.health_samples").fetchone()[0] == n


@pytest.mark.parametrize(
    "stmt",
    [
        "insert into public.health_samples (user_id, hk_uuid, type, start_date, end_date, value, unit)"
        f" values ('{ME}', gen_random_uuid(), 'x', now(), now(), 1, 'x')",
        "update public.health_samples set value = 0",
        "delete from public.health_samples",
        "truncate public.health_samples",
        "create table public.evil (id int)",
    ],
)
def test_reader_cannot_write_even_in_a_read_write_transaction(db, seeded, stmt):
    with psycopg.connect(db["reader"]) as c:
        with pytest.raises(errors.ReadOnlySqlTransaction):
            c.execute(stmt)
        c.rollback()
        c.execute("set transaction read write")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute(stmt)


def test_reader_cannot_see_other_tables(db):
    with psycopg.connect(db["reader"]) as c:
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("select * from auth.users")


def test_grants_are_exactly_select_on_health_samples(db):
    with psycopg.connect(db["admin"]) as c:
        grants = c.execute(
            "select table_schema, table_name, privilege_type from information_schema.role_table_grants"
            " where grantee = 'healthsync_reader'"
        ).fetchall()
    assert grants == [("public", "health_samples", "SELECT")]


def test_script_refuses_placeholder_password(db):
    with psycopg.connect(db["owner"], autocommit=True) as c:
        with pytest.raises(errors.RaiseException):
            c.execute(READER_SQL.read_text())


def test_script_is_rerunnable(db):
    with psycopg.connect(db["owner"], autocommit=True) as c:
        c.execute(READER_SQL.read_text().replace("REPLACE_WITH_A_STRONG_PASSWORD", READER_PW))


# ---------------------------------------------------------------- SQL == Python


@pytest.fixture(scope="module")
def sources(db, seeded):
    data, _ = seeded
    settings = load_settings({"DATABASE_URL": db["reader"], "HEALTH_USER_ID": str(ME)})
    pg = PostgresSource(settings)
    pg.pool.wait(timeout=10)
    mem = MemorySource(data, settings)
    yield pg, mem
    pg.close()


FROM, TO = date(2026, 9, 20), date(2026, 11, 11)


def assert_same(a, b, path="$"):
    """Equal, except floats may differ by one rounding step: Postgres and Python add up
    floating-point numbers in a different order, so an average of x.x5 can round either way."""
    if isinstance(a, dict):
        assert isinstance(b, dict) and a.keys() == b.keys(), path
        for k in a:
            assert_same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            assert_same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, (int, float)):
        assert a == pytest.approx(b, abs=0.1 + 1e-9), path
    else:
        assert a == b, path


@pytest.mark.parametrize("key", list(hk.METRICS))
def test_daily_matches_in_memory(sources, key):
    pg, mem = sources
    m = hk.METRICS[key]
    assert_same(service.daily(pg, m, FROM, TO, TZ), service.daily(mem, m, FROM, TO, TZ))


@pytest.mark.parametrize("fn", [service.sleep, service.workouts, service.heart, service.body])
def test_endpoints_match_in_memory(sources, fn):
    pg, mem = sources
    assert_same(fn(pg, FROM, TO, TZ), fn(mem, FROM, TO, TZ))


def test_summary_matches_in_memory(sources):
    pg, mem = sources
    assert_same(service.summary(pg, 7, TZ, now=NOW), service.summary(mem, 7, TZ, now=NOW))


def test_ping_and_last_upload(sources):
    pg, _ = sources
    assert pg.ping() is True
    assert pg.last_upload() is not None


def test_unfiltered_reader_sees_other_accounts(db, seeded):
    settings = load_settings({"DATABASE_URL": db["reader"]})
    pg = PostgresSource(settings)
    try:
        pg.pool.wait(timeout=10)
        assert pg.latest(hk.BODY_MASS).value == 55.0  # the other account's newer row
    finally:
        pg.close()
