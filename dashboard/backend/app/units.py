"""How stored units are shown, and the labels for category values.

The iPhone app stores each type in one canonical HealthKit unit. Two need converting
before a human sees them:

* "%" is HealthKit's percent unit, which stores a FRACTION (0.97 means 97%). We multiply
  by 100 here, once, so every endpoint agrees.
* Small nutrition amounts are stored in grams. The frontend auto-scales g -> mg -> µg per
  value; the API keeps grams so sums stay in one unit.
"""

from __future__ import annotations

from . import hktypes as hk

DISPLAY_UNITS = {
    "count/min": "bpm",
    "count": "",
    "degC": "°C",
    "dBASPL": "dB",
    "ml/(kg*min)": "mL/kg/min",
    "kcal/(kg*hr)": "kcal/kg/hr",
    "appleEffortScore": "effort",
    "S": "S",
    "%": "%",
    "min": "min",
}

# Rate types stored as count/min that aren't heart beats.
_PER_MIN_OVERRIDES = {"HKQuantityTypeIdentifierRespiratoryRate": "breaths/min"}


def display(type_id: str, unit: str | None) -> tuple[str, float]:
    """(display unit, multiplier to apply to stored values)."""
    if unit is None:
        return "", 1.0
    if unit == "%":
        return "%", 100.0
    if unit == "count/min" and type_id in _PER_MIN_OVERRIDES:
        return _PER_MIN_OVERRIDES[type_id], 1.0
    return DISPLAY_UNITS.get(unit, unit), 1.0


SLEEP_LABELS = {
    hk.SLEEP_IN_BED: "In bed",
    hk.SLEEP_UNSPECIFIED: "Asleep",
    hk.SLEEP_AWAKE: "Awake",
    hk.SLEEP_CORE: "Core",
    hk.SLEEP_DEEP: "Deep",
    hk.SLEEP_REM: "REM",
}

# HKCategoryValueSeverity, used by every symptom type.
SEVERITY_LABELS = {0: "Unspecified", 1: "Not present", 2: "Mild", 3: "Moderate", 4: "Severe"}


def category_label(type_id: str, group: str, value: float) -> str:
    v = int(value)
    if type_id == hk.SLEEP:
        return SLEEP_LABELS.get(v, f"Value {v}")
    if group == "Symptoms":
        return SEVERITY_LABELS.get(v, f"Value {v}")
    return f"Value {v}"
