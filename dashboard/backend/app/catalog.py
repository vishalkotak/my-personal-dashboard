"""The catalog of every HealthKit type the iPhone app can upload.

The app ships its list as `apple-health-sync/HealthSync/HealthTypes.json`:

    [{"id": "HKQuantityTypeIdentifierStepCount", "kind": "quantity", "group": "Fitness",
      "name": "Step Count", "unit": "count", "aggregation": "sum"}, ...]

We read that file (path configurable with HEALTH_TYPES_PATH). If it isn't there, we fall
back to a small built-in list and to whatever types actually appear in the database,
treating unknown quantity types as "average" and categories as "duration".

The catalog is also the allowlist for the generic /api/metric endpoint.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

from . import hktypes as hk

log = logging.getLogger(__name__)

Aggregation = Literal["sum", "average", "duration"]
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "apple-health-sync" / "HealthSync" / "HealthTypes.json"


@dataclass(frozen=True)
class TypeInfo:
    id: str
    kind: str          # quantity | category | workout
    group: str
    name: str
    unit: str | None   # stored unit; None for categories
    aggregation: Aggregation

    def to_dict(self) -> dict:
        return asdict(self)


# Built-in entries: the original 13 types plus the extras the demo data uses. Used when
# the app's catalog file isn't available, and to fill gaps in it.
_BUILTIN = [
    (hk.STEPS, "quantity", "Fitness", "Step Count", "count", "sum"),
    (hk.DISTANCE, "quantity", "Fitness", "Walking + Running Distance", "m", "sum"),
    (hk.ACTIVE_ENERGY, "quantity", "Fitness", "Active Energy", "kcal", "sum"),
    ("HKQuantityTypeIdentifierFlightsClimbed", "quantity", "Fitness", "Flights Climbed", "count", "sum"),
    ("HKQuantityTypeIdentifierVO2Max", "quantity", "Fitness", "VO2 Max", "ml/(kg*min)", "average"),
    (hk.HEART_RATE, "quantity", "Heart", "Heart Rate", "count/min", "average"),
    (hk.RESTING_HR, "quantity", "Heart", "Resting Heart Rate", "count/min", "average"),
    (hk.HRV, "quantity", "Heart", "Heart Rate Variability", "ms", "average"),
    (hk.BODY_MASS, "quantity", "Body Measurements", "Body Mass", "kg", "average"),
    (hk.BP_SYSTOLIC, "quantity", "Vital Signs", "Blood Pressure Systolic", "mmHg", "average"),
    (hk.BP_DIASTOLIC, "quantity", "Vital Signs", "Blood Pressure Diastolic", "mmHg", "average"),
    (hk.SPO2, "quantity", "Respiratory", "Blood Oxygen", "%", "average"),
    ("HKQuantityTypeIdentifierRespiratoryRate", "quantity", "Respiratory", "Respiratory Rate", "count/min", "average"),
    (hk.BODY_TEMP, "quantity", "Vital Signs", "Body Temperature", "degC", "average"),
    ("HKQuantityTypeIdentifierDietaryWater", "quantity", "Nutrition", "Water", "mL", "sum"),
    ("HKQuantityTypeIdentifierDietaryProtein", "quantity", "Nutrition", "Protein", "g", "sum"),
    (hk.SLEEP, "category", "Sleep", "Sleep Analysis", None, "duration"),
    ("HKCategoryTypeIdentifierMindfulSession", "category", "Mindfulness", "Mindful Minutes", None, "duration"),
    ("HKCategoryTypeIdentifierHeadache", "category", "Symptoms", "Headache", None, "duration"),
    (hk.WORKOUT, "workout", "Fitness", "Workouts", "s", "duration"),
]

_PREFIXES = ("HKQuantityTypeIdentifier", "HKCategoryTypeIdentifier", "HKCorrelationTypeIdentifier",
             "HKDataTypeIdentifier", "HKWorkoutTypeIdentifier")


def pretty_name(type_id: str) -> str:
    """HKQuantityTypeIdentifierDietaryVitaminB12 -> 'Dietary Vitamin B12'."""
    s = type_id
    for p in _PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    s = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[0-9])(?=[A-Z])", " ", s)
    return s.strip() or type_id


def guess(type_id: str, unit: str | None) -> TypeInfo:
    """Best guess for a type we know nothing about (catalog missing it)."""
    if type_id == hk.WORKOUT:
        return TypeInfo(type_id, "workout", "Fitness", "Workouts", "s", "duration")
    if type_id.startswith("HKCategoryTypeIdentifier") or unit == "category":
        return TypeInfo(type_id, "category", "Other", pretty_name(type_id), None, "duration")
    return TypeInfo(type_id, "quantity", "Other", pretty_name(type_id), unit, "average")


class Catalog:
    def __init__(self, entries: Iterable[TypeInfo], source: str):
        self.by_id: dict[str, TypeInfo] = {}
        for e in entries:
            self.by_id.setdefault(e.id, e)
        self.source = source  # "file" or "builtin"

    def get(self, type_id: str) -> TypeInfo | None:
        return self.by_id.get(type_id)

    def __contains__(self, type_id: str) -> bool:
        return type_id in self.by_id

    def add_discovered(self, type_id: str, unit: str | None) -> TypeInfo:
        """Register a type seen in the database but missing from the catalog."""
        if type_id not in self.by_id:
            self.by_id[type_id] = guess(type_id, unit)
        return self.by_id[type_id]


def _parse(raw: object) -> list[TypeInfo]:
    if not isinstance(raw, list):
        raise ValueError("catalog must be a JSON array")
    out = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        tid = item["id"]
        if len(tid) > 128:
            continue
        kind = item.get("kind") if item.get("kind") in ("quantity", "category", "workout") else None
        agg = item.get("aggregation")
        if agg not in ("sum", "average", "duration"):
            agg = "duration" if kind in ("category", "workout") else "average"
        unit = item.get("unit") if isinstance(item.get("unit"), str) else None
        out.append(
            TypeInfo(
                id=tid,
                kind=kind or ("category" if unit is None else "quantity"),
                group=str(item.get("group") or "Other"),
                name=str(item.get("name") or pretty_name(tid)),
                unit=unit,
                aggregation=agg,
            )
        )
    return out


def builtin_entries() -> list[TypeInfo]:
    return [TypeInfo(*row) for row in _BUILTIN]


def load_catalog(path: Path | None = None) -> Catalog:
    path = path or DEFAULT_PATH
    try:
        entries = _parse(json.loads(Path(path).read_text()))
        log.info("loaded %d types from %s", len(entries), path)
        # File wins; built-ins only fill in anything it doesn't mention.
        return Catalog([*entries, *builtin_entries()], source="file")
    except FileNotFoundError:
        log.info("no type catalog at %s; using built-in list + types found in the data", path)
    except (ValueError, OSError) as e:
        log.warning("could not read type catalog %s (%s); using built-in list", path, e)
    return Catalog(builtin_entries(), source="builtin")
