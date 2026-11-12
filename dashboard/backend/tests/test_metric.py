"""The type catalog, unit handling and the generic /api/metric aggregation."""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import hktypes as hk
from app import units
from app.api import create_app
from app.catalog import DEFAULT_PATH, Catalog, builtin_entries, guess, load_catalog, pretty_name
from app.dedupe import Sample
from app.sources import MemorySource

from .test_api import SETTINGS, demo_client  # noqa: F401
from .test_dedupe import la, s

PROTEIN = "HKQuantityTypeIdentifierDietaryProtein"
VO2 = "HKQuantityTypeIdentifierVO2Max"
HEADACHE = "HKCategoryTypeIdentifierHeadache"
MINDFUL = "HKCategoryTypeIdentifierMindfulSession"
EXERCISE = "HKQuantityTypeIdentifierAppleExerciseTime"
BODY_FAT = "HKQuantityTypeIdentifierBodyFatPercentage"


# ---------------------------------------------------------------- catalog


def test_real_catalog_from_the_app_loads():
    cat = load_catalog(DEFAULT_PATH)
    assert cat.source == "file"
    assert len(cat.by_id) >= 189
    steps = cat.get(hk.STEPS)
    assert (steps.aggregation, steps.unit, steps.kind) == ("sum", "count", "quantity")
    assert cat.get(hk.HEART_RATE).aggregation == "average"
    assert cat.get(HEADACHE).kind == "category" and cat.get(HEADACHE).unit is None
    # The original 13 types keep the units the dashboard expects.
    for m in hk.METRICS.values():
        assert cat.get(m.hk_type).unit == m.unit, m.key


def test_missing_catalog_falls_back_to_builtin(tmp_path):
    cat = load_catalog(tmp_path / "nope.json")
    assert cat.source == "builtin" and hk.STEPS in cat and PROTEIN in cat


def test_bad_catalog_entries_are_skipped(tmp_path):
    p = tmp_path / "types.json"
    p.write_text(json.dumps([
        {"id": "HKQuantityTypeIdentifierFoo", "kind": "quantity", "unit": "g", "aggregation": "sum", "group": "Nutrition", "name": "Foo"},
        {"id": "HKCategoryTypeIdentifierBar", "kind": "category", "aggregation": "weird"},
        {"nope": 1},
        "string",
    ]))
    cat = load_catalog(p)
    assert cat.get("HKQuantityTypeIdentifierFoo").aggregation == "sum"
    bar = cat.get("HKCategoryTypeIdentifierBar")
    assert (bar.aggregation, bar.group, bar.name) == ("duration", "Other", "Bar")
    p.write_text("{not json")
    assert load_catalog(p).source == "builtin"


def test_unknown_types_are_guessed():
    assert guess("HKQuantityTypeIdentifierNewThing", "g").aggregation == "average"
    assert guess("HKCategoryTypeIdentifierNewEvent", "category").aggregation == "duration"
    cat = Catalog(builtin_entries(), "builtin")
    info = cat.add_discovered("HKQuantityTypeIdentifierNewThing", "mg/dL")
    assert info.name == "New Thing" and cat.get(info.id) is info


@pytest.mark.parametrize(
    "tid,name",
    [
        ("HKQuantityTypeIdentifierDietaryVitaminB12", "Dietary Vitamin B12"),
        ("HKQuantityTypeIdentifierVO2Max", "VO2 Max"),
        ("HKCategoryTypeIdentifierAppleStandHour", "Apple Stand Hour"),
    ],
)
def test_pretty_name(tid, name):
    assert pretty_name(tid) == name


# ---------------------------------------------------------------- units


@pytest.mark.parametrize(
    "tid,unit,expected",
    [
        (hk.SPO2, "%", ("%", 100.0)),
        (BODY_FAT, "%", ("%", 100.0)),
        (hk.HEART_RATE, "count/min", ("bpm", 1.0)),
        ("HKQuantityTypeIdentifierRespiratoryRate", "count/min", ("breaths/min", 1.0)),
        (EXERCISE, "min", ("min", 1.0)),
        (hk.BODY_TEMP, "degC", ("°C", 1.0)),
        (PROTEIN, "g", ("g", 1.0)),
        (VO2, "ml/(kg*min)", ("mL/kg/min", 1.0)),
        (HEADACHE, None, ("", 1.0)),
    ],
)
def test_display_units(tid, unit, expected):
    assert units.display(tid, unit) == expected


def test_category_labels():
    assert units.category_label(HEADACHE, "Symptoms", 4) == "Severe"
    assert units.category_label(hk.SLEEP, "Sleep", 4) == "Deep"
    assert units.category_label(MINDFUL, "Mindfulness", 7) == "Value 7"


# ---------------------------------------------------------------- /api/metric


def client(by_type, unit_map=None):
    return TestClient(create_app(SETTINGS, MemorySource(by_type, SETTINGS, units=unit_map or {}), load_catalog()))


def get(c, tid, frm="2026-03-01", to="2026-03-02"):
    r = c.get(f"/api/metric?type={tid}&from={frm}&to={to}")
    assert r.status_code == 200, r.text
    return r.json()


def test_sum_type_is_deduped_like_steps():
    t = la(2026, 3, 1, 9)
    # Exercise minutes from phone (one 10-min sample) and watch (ten 1-min samples).
    data = {EXERCISE: [s(t, 10, 9)] + [s(t + timedelta(minutes=i), 1, 1) for i in range(10)]}
    with client(data) as c:
        body = get(c, EXERCISE)
    assert body["aggregation"] == "sum" and body["approximate"] is True
    assert body["display_unit"] == "min"
    assert body["points"][0] == {"date": "2026-03-01", "value": 10, "raw_sum": 19}
    assert body["points"][1]["value"] is None


def test_sum_of_point_samples_counts_duplicates_once():
    t = la(2026, 3, 1, 12)
    data = {PROTEIN: [s(t, 0, 30), s(t, 0, 30), s(t + timedelta(hours=6), 0, 0.0000024)]}
    with client(data) as c:
        p = get(c, PROTEIN)["points"][0]
    assert p["value"] == pytest.approx(30.0000024) and p["raw_sum"] == pytest.approx(60.0000024)


def test_small_values_keep_significant_digits():
    t = la(2026, 3, 1, 12)
    b12 = "HKQuantityTypeIdentifierDietaryVitaminB12"
    with client({b12: [s(t, 0, 0.0000024)]}) as c:
        assert get(c, b12)["points"][0]["value"] == 0.0000024


def test_average_type_and_percent_scaling():
    t = la(2026, 3, 1, 8)
    with client({BODY_FAT: [s(t, 0, 0.18), s(t + timedelta(hours=2), 0, 0.20)]}) as c:
        body = get(c, BODY_FAT)
    assert body["aggregation"] == "average" and body["display_unit"] == "%"
    p = body["points"][0]
    assert (p["avg"], p["min"], p["max"], p["count"]) == (pytest.approx(19.0), 18.0, 20.0, 2)


def test_duration_category_with_values_breaks_down():
    data = {
        HEADACHE: [
            Sample(la(2026, 3, 1, 10), la(2026, 3, 1, 11), 2),
            Sample(la(2026, 3, 1, 15), la(2026, 3, 1, 15, 30), 4),
        ]
    }
    with client(data) as c:
        body = get(c, HEADACHE)
    assert body["aggregation"] == "duration" and body["labels"] == ["Mild", "Severe"]
    assert body["points"][0] == {
        "date": "2026-03-01", "minutes": 90.0, "count": 2, "breakdown": {"Mild": 60.0, "Severe": 30.0}
    }


def test_duration_category_without_values_has_no_breakdown():
    data = {MINDFUL: [Sample(la(2026, 3, 1, 7), la(2026, 3, 1, 7, 10), 0), Sample(la(2026, 3, 1, 21), la(2026, 3, 1, 21, 5), 0)]}
    with client(data) as c:
        body = get(c, MINDFUL)
    assert body["labels"] == [] and body["points"][0]["minutes"] == 15 and body["points"][0]["count"] == 2


def test_sleep_in_explore_uses_dedupe():
    bed = la(2026, 3, 1, 23)
    data = {hk.SLEEP: [s(bed, 480, hk.SLEEP_IN_BED), s(bed, 480, hk.SLEEP_IN_BED), s(bed + timedelta(minutes=30), 60, hk.SLEEP_DEEP)]}
    with client(data) as c:
        body = get(c, hk.SLEEP)
    night = body["points"][1]
    assert body["per"] == "night" and night["minutes"] == 480
    assert night["breakdown"] == {"Deep": 60.0, "In bed": 420.0}


def test_workouts_in_explore_are_minutes():
    data = {hk.WORKOUT: [Sample(la(2026, 3, 1, 7), la(2026, 3, 1, 7, 45), 2700, {"activity_type": "37"})]}
    with client(data) as c:
        p = get(c, hk.WORKOUT)["points"][0]
    assert (p["minutes"], p["count"]) == (45.0, 1)


def test_metric_rejects_unknown_and_malformed_types():
    with client({}) as c:
        for bad in ["HKQuantityTypeIdentifierBogus", "steps", "'; drop table x", "x" * 200]:
            assert c.get(f"/api/metric?type={bad}").status_code == 422


def test_type_seen_in_data_but_not_in_catalog_is_usable():
    new = "HKQuantityTypeIdentifierBrandNewThing"
    with client({new: [s(la(2026, 3, 1, 9), 0, 5)]}, {new: "mg/dL"}) as c:
        types = {t["id"]: t for t in c.get("/api/types").json()["types"]}
        assert types[new]["aggregation"] == "average" and types[new]["group"] == "Other"
        assert get(c, new)["points"][0]["avg"] == 5


def test_types_lists_only_types_with_data():
    data = {PROTEIN: [s(la(2026, 3, 1, 9), 0, 5)], hk.STEPS: [s(la(2026, 3, 2, 9), 5, 100)]}
    with client(data, {PROTEIN: "g", hk.STEPS: "count"}) as c:
        body = c.get("/api/types").json()
    assert body["catalog_source"] == "file" and body["catalog_size"] >= 189
    assert {t["id"] for t in body["types"]} == {PROTEIN, hk.STEPS}
    protein = next(t for t in body["types"] if t["id"] == PROTEIN)
    assert protein["group"] == "Nutrition" and protein["count"] == 1 and protein["latest"].startswith("2026-03-01")


def test_demo_types_cover_explore(demo_client):
    body = demo_client.get("/api/types").json()
    assert len(body["types"]) == 20
    assert {"Nutrition", "Symptoms", "Mindfulness", "Respiratory"} <= {t["group"] for t in body["types"]}
