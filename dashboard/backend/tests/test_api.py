from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import hktypes as hk
from app.api import MAX_RANGE_DAYS, create_app
from app.config import load_settings
from app.dedupe import Sample
from app.sources import MemorySource

from .test_dedupe import LA, la, s

# Pin "now" so the demo data and "today" don't depend on when the tests run.
SETTINGS = load_settings({"DEMO": "1", "TZ_NAME": "America/Los_Angeles", "DEMO_NOW": "2026-11-11T18:00:00-08:00"})


@pytest.fixture(scope="module")
def demo_client():
    with TestClient(create_app(SETTINGS)) as c:
        yield c


def small_client(by_type):
    return TestClient(create_app(SETTINGS, MemorySource(by_type, SETTINGS)))


# ---------------------------------------------------------------- read-only surface


def test_every_route_is_get_only():
    app = create_app(SETTINGS, MemorySource({}, SETTINGS))
    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    assert routes, "expected API routes"
    for r in routes:
        assert r.methods <= {"GET", "HEAD"}, f"{r.path} allows {r.methods}"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize("path", ["/api/daily?type=steps", "/api/sleep", "/api/summary", "/api/health"])
def test_write_methods_are_rejected(demo_client, method, path):
    assert getattr(demo_client, method)(path).status_code == 405


def test_unknown_host_is_rejected():
    with small_client({}) as c:
        assert c.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_cors_only_allows_local_frontend(demo_client):
    ok = demo_client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = demo_client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "query",
    [
        "type=DROP TABLE",
        "type=HKQuantityTypeIdentifierDietaryCaffeine",
        "type=steps;select",
        "type=steps&from=2026-03-10&to=2026-03-01",
        "type=steps&from=not-a-date",
        "type=steps&from=1990-01-01&to=1990-02-01",
        "type=steps&from=2026-01-01&to=2099-01-01",
        f"type=steps&from={(date(2026, 1, 1) - timedelta(days=MAX_RANGE_DAYS)).isoformat()}&to=2026-01-01",
        "type=" + "x" * 100,
    ],
)
def test_daily_rejects_bad_input(demo_client, query):
    assert demo_client.get(f"/api/daily?{query}").status_code == 422


def test_daily_requires_type(demo_client):
    assert demo_client.get("/api/daily").status_code == 422


def test_daily_accepts_full_hk_identifier(demo_client):
    r = demo_client.get(f"/api/daily?type={hk.HRV}&from=2026-01-01&to=2026-01-07")
    assert r.status_code == 200 and r.json()["type"] == "hrv"


def test_three_year_range_is_allowed(demo_client):
    to = date(2026, 11, 10)
    frm = to - timedelta(days=MAX_RANGE_DAYS - 1)
    assert demo_client.get(f"/api/sleep?from={frm}&to={to}").status_code == 200


@pytest.mark.parametrize("days", [0, 91, -1, "abc"])
def test_summary_days_validated(demo_client, days):
    assert demo_client.get(f"/api/summary?days={days}").status_code == 422


# ---------------------------------------------------------------- shapes & correctness


def test_health(demo_client):
    body = demo_client.get("/api/health").json()
    assert body["ok"] and body["demo"] and body["database_reachable"]
    assert body["tz"] == "America/Los_Angeles"


def test_daily_cumulative_dedupes_and_reports_raw():
    t = la(2026, 3, 1, 9)
    phone = [s(t, 10, 900)]
    watch = [s(t + timedelta(minutes=i), 1, 100) for i in range(10)]
    with small_client({hk.STEPS: phone + watch}) as c:
        body = c.get("/api/daily?type=steps&from=2026-03-01&to=2026-03-02").json()
    assert body["approximate"] is True and "Approximate" in body["note"]
    assert body["points"] == [
        {"date": "2026-03-01", "value": 1000, "raw_sum": 1900},
        {"date": "2026-03-02", "value": None, "raw_sum": None},
    ]


def test_daily_spo2_is_scaled_to_percent():
    t = la(2026, 3, 1, 3)
    with small_client({hk.SPO2: [s(t, 0, 0.95), s(t + timedelta(hours=1), 0, 0.97)]}) as c:
        [p] = c.get("/api/daily?type=spo2&from=2026-03-01&to=2026-03-01").json()["points"]
    assert (p["avg"], p["min"], p["max"], p["count"]) == (96.0, 95.0, 97.0, 2)


def test_sleep_endpoint_groups_nights():
    bed = la(2026, 3, 1, 23)
    data = {hk.SLEEP: [s(bed, 480, hk.SLEEP_IN_BED), s(bed + timedelta(minutes=10), 60, hk.SLEEP_DEEP)]}
    with small_client(data) as c:
        nights = c.get("/api/sleep?from=2026-03-01&to=2026-03-02").json()["nights"]
    assert nights[0] == {"night": "2026-03-01", "has_data": False}
    n = nights[1]
    assert n["night"] == "2026-03-02" and n["deep_min"] == 60 and n["in_bed_min"] == 480
    assert n["asleep_min"] == 60 and n["staged"] is True


def test_workouts_endpoint_names_and_weekly_totals():
    data = {
        hk.WORKOUT: [
            Sample(la(2026, 3, 2, 7), la(2026, 3, 2, 7, 30), 1800, {"activity_type": "37"}),
            Sample(la(2026, 3, 4, 18), la(2026, 3, 4, 19), 3600, {"activity_type": "50"}),
            Sample(la(2026, 3, 10, 18), la(2026, 3, 10, 18, 20), 1200, {"activity_type": "12345"}),
            Sample(la(2026, 3, 11, 18), la(2026, 3, 11, 18, 20), 1200, {}),
        ]
    }
    with small_client(data) as c:
        body = c.get("/api/workouts?from=2026-03-01&to=2026-03-14").json()
    assert [w["name"] for w in body["workouts"]] == ["Other", "Other", "Traditional strength training", "Running"]
    assert body["weekly"] == [
        {"week_start": "2026-02-23", "minutes": 0.0, "count": 0},
        {"week_start": "2026-03-02", "minutes": 90.0, "count": 2},
        {"week_start": "2026-03-09", "minutes": 40.0, "count": 2},
    ]
    assert body["by_type"][0] == {"name": "Traditional strength training", "count": 1, "minutes": 60.0}


def test_body_pairs_blood_pressure_and_counts_unpaired():
    t = la(2026, 3, 1, 9)
    data = {
        hk.BP_SYSTOLIC: [s(t, 0, 121), s(t + timedelta(hours=2), 0, 140)],
        hk.BP_DIASTOLIC: [s(t, 0, 79)],
        hk.BODY_MASS: [s(t, 0, 80.0), s(t + timedelta(hours=1), 0, 79.6)],
    }
    with small_client(data) as c:
        body = c.get("/api/body?from=2026-03-01&to=2026-03-01").json()
    assert [(b["systolic"], b["diastolic"]) for b in body["blood_pressure"]] == [(121, 79)]
    assert body["unpaired_bp_readings"] == 1
    assert body["days"][0]["weight"] == 79.6  # last reading of the day


def test_empty_database_gives_empty_but_valid_responses():
    with small_client({}) as c:
        summary = c.get("/api/summary").json()["cards"]
        assert summary["steps"]["today"] is None
        assert summary["weight"]["latest"] is None
        assert summary["sleep"]["last_night"] is None
        assert c.get("/api/workouts").json()["workouts"] == []
        assert all(not n["has_data"] for n in c.get("/api/sleep").json()["nights"])
        assert all(d["hr_avg"] is None for d in c.get("/api/heart").json()["days"])


def test_summary_shape(demo_client):
    body = demo_client.get("/api/summary?days=7").json()
    cards = body["cards"]
    assert set(cards) == {"steps", "active_energy", "resting_hr", "hrv", "sleep", "weight"}
    for c in cards.values():
        assert len(c["spark"]) == 30
    assert cards["steps"]["today"] > 0 and cards["steps"]["approximate"] is True
    assert 40 < cards["resting_hr"]["latest"] < 75
    assert cards["sleep"]["last_night"]["asleep_min"] > 200
    assert 70 < cards["weight"]["latest"] < 90


def test_errors_do_not_leak_details():
    class Broken(MemorySource):
        def daily_stats(self, *a):
            raise RuntimeError("postgresql://user:secret@host/db")

    app = create_app(SETTINGS, Broken({}, SETTINGS))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/daily?type=hrv")
    assert r.status_code == 500 and "secret" not in r.text
