"""The HealthKit types the iPhone app uploads, and how each one should be aggregated.

This is also the allowlist for any user-supplied `type` parameter: anything not in
`METRICS` is rejected before it gets anywhere near a query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["cumulative", "discrete", "sleep", "workout"]

STEPS = "HKQuantityTypeIdentifierStepCount"
DISTANCE = "HKQuantityTypeIdentifierDistanceWalkingRunning"
ACTIVE_ENERGY = "HKQuantityTypeIdentifierActiveEnergyBurned"
HEART_RATE = "HKQuantityTypeIdentifierHeartRate"
RESTING_HR = "HKQuantityTypeIdentifierRestingHeartRate"
HRV = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
BODY_MASS = "HKQuantityTypeIdentifierBodyMass"
BP_SYSTOLIC = "HKQuantityTypeIdentifierBloodPressureSystolic"
BP_DIASTOLIC = "HKQuantityTypeIdentifierBloodPressureDiastolic"
SPO2 = "HKQuantityTypeIdentifierOxygenSaturation"
BODY_TEMP = "HKQuantityTypeIdentifierBodyTemperature"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
WORKOUT = "HKWorkoutTypeIdentifier"


@dataclass(frozen=True)
class Metric:
    key: str          # short, URL-friendly name used by the API
    hk_type: str      # value stored in health_samples.type
    kind: Kind
    unit: str         # unit as stored
    label: str
    display_unit: str
    scale: float = 1.0  # multiply stored value by this for display (SpO2 fraction -> %)


METRICS: dict[str, Metric] = {
    m.key: m
    for m in [
        Metric("steps", STEPS, "cumulative", "count", "Steps", "steps"),
        Metric("distance", DISTANCE, "cumulative", "m", "Walking + running distance", "m"),
        Metric("active_energy", ACTIVE_ENERGY, "cumulative", "kcal", "Active energy", "kcal"),
        Metric("heart_rate", HEART_RATE, "discrete", "count/min", "Heart rate", "bpm"),
        Metric("resting_hr", RESTING_HR, "discrete", "count/min", "Resting heart rate", "bpm"),
        Metric("hrv", HRV, "discrete", "ms", "Heart rate variability (SDNN)", "ms"),
        Metric("body_mass", BODY_MASS, "discrete", "kg", "Weight", "kg"),
        Metric("bp_systolic", BP_SYSTOLIC, "discrete", "mmHg", "Blood pressure (systolic)", "mmHg"),
        Metric("bp_diastolic", BP_DIASTOLIC, "discrete", "mmHg", "Blood pressure (diastolic)", "mmHg"),
        Metric("spo2", SPO2, "discrete", "%", "Blood oxygen", "%", scale=100.0),
        Metric("body_temp", BODY_TEMP, "discrete", "degC", "Body temperature", "°C"),
    ]
}

# Accept either the short key or the full HealthKit identifier.
_BY_HK = {m.hk_type: m for m in METRICS.values()}


def lookup_metric(name: str) -> Metric | None:
    return METRICS.get(name) or _BY_HK.get(name)


ALL_HK_TYPES = frozenset([*_BY_HK, SLEEP, WORKOUT])

# HKCategoryValueSleepAnalysis raw values.
SLEEP_IN_BED = 0
SLEEP_UNSPECIFIED = 1
SLEEP_AWAKE = 2
SLEEP_CORE = 3
SLEEP_DEEP = 4
SLEEP_REM = 5

# HKWorkoutActivityType raw values -> readable names (the common ones; anything else is "Other").
WORKOUT_NAMES: dict[int, str] = {
    1: "American football",
    2: "Archery",
    3: "Australian football",
    4: "Badminton",
    5: "Baseball",
    6: "Basketball",
    7: "Bowling",
    8: "Boxing",
    9: "Climbing",
    10: "Cricket",
    11: "Cross training",
    12: "Curling",
    13: "Cycling",
    14: "Dance",
    15: "Dance-inspired training",
    16: "Elliptical",
    17: "Equestrian sports",
    18: "Fencing",
    19: "Fishing",
    20: "Functional strength training",
    21: "Golf",
    22: "Gymnastics",
    23: "Handball",
    24: "Hiking",
    25: "Hockey",
    26: "Hunting",
    27: "Lacrosse",
    28: "Martial arts",
    29: "Mind and body",
    30: "Mixed metabolic cardio",
    31: "Paddle sports",
    32: "Play",
    33: "Preparation and recovery",
    34: "Racquetball",
    35: "Rowing",
    36: "Rugby",
    37: "Running",
    38: "Sailing",
    39: "Skating",
    40: "Snow sports",
    41: "Soccer",
    42: "Softball",
    43: "Squash",
    44: "Stair climbing",
    45: "Surfing",
    46: "Swimming",
    47: "Table tennis",
    48: "Tennis",
    49: "Track and field",
    50: "Traditional strength training",
    51: "Volleyball",
    52: "Walking",
    53: "Water fitness",
    54: "Water polo",
    55: "Water sports",
    56: "Wrestling",
    57: "Yoga",
    58: "Barre",
    59: "Core training",
    60: "Cross-country skiing",
    61: "Downhill skiing",
    62: "Flexibility",
    63: "HIIT",
    64: "Jump rope",
    65: "Kickboxing",
    66: "Pilates",
    67: "Snowboarding",
    68: "Stairs",
    69: "Step training",
    70: "Wheelchair walk pace",
    71: "Wheelchair run pace",
    72: "Tai chi",
    73: "Mixed cardio",
    74: "Hand cycling",
    75: "Disc sports",
    76: "Fitness gaming",
    77: "Cardio dance",
    78: "Social dance",
    79: "Pickleball",
    80: "Cooldown",
    82: "Swim + bike + run",
    83: "Transition",
    84: "Underwater diving",
    3000: "Other",
}


def workout_name(activity_type: object) -> str:
    try:
        return WORKOUT_NAMES.get(int(str(activity_type)), "Other")
    except (TypeError, ValueError):
        return "Other"
