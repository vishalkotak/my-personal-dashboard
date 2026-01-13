"""
Pydantic models for WHOOP API responses.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ========== User Models ==========

class UserProfile(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str


class BodyMeasurements(BaseModel):
    height_meter: float
    weight_kilogram: float
    max_heart_rate: int


# ========== Cycle Models ==========

class CycleScore(BaseModel):
    strain: float
    kilojoule: float
    average_heart_rate: int
    max_heart_rate: int


class Cycle(BaseModel):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: Optional[datetime] = None
    timezone_offset: str
    score_state: str
    score: Optional[CycleScore] = None


# ========== Recovery Models ==========

class RecoveryScore(BaseModel):
    user_calibrating: bool = False
    recovery_score: Optional[float] = None
    resting_heart_rate: Optional[float] = None
    hrv_rmssd_milli: Optional[float] = Field(None, description="Heart Rate Variability in milliseconds")
    spo2_percentage: Optional[float] = Field(None, description="Blood oxygen percentage")
    skin_temp_celsius: Optional[float] = None


class Recovery(BaseModel):
    cycle_id: int
    sleep_id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    score_state: str
    score: Optional[RecoveryScore] = None


# ========== Sleep Models ==========

class SleepStageSummary(BaseModel):
    total_in_bed_time_milli: int = 0
    total_awake_time_milli: int = 0
    total_no_data_time_milli: int = 0
    total_light_sleep_time_milli: int = 0
    total_slow_wave_sleep_time_milli: int = Field(0, description="Deep sleep duration")
    total_rem_sleep_time_milli: int = 0
    sleep_cycle_count: int = 0
    disturbance_count: int = 0


class SleepNeeded(BaseModel):
    baseline_milli: int = 0
    need_from_sleep_debt_milli: int = 0
    need_from_recent_strain_milli: int = 0
    need_from_recent_nap_milli: int = 0


class SleepScore(BaseModel):
    stage_summary: Optional[SleepStageSummary] = None
    sleep_needed: Optional[SleepNeeded] = None
    respiratory_rate: Optional[float] = None
    sleep_performance_percentage: Optional[float] = None
    sleep_consistency_percentage: Optional[float] = None
    sleep_efficiency_percentage: Optional[float] = None


class Sleep(BaseModel):
    id: str
    cycle_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime
    timezone_offset: str
    nap: bool = False
    score_state: str
    score: Optional[SleepScore] = None


# ========== Workout Models ==========

class WorkoutScore(BaseModel):
    strain: Optional[float] = None
    average_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    kilojoule: Optional[float] = None
    percent_recorded: Optional[float] = None
    distance_meter: Optional[float] = None
    altitude_gain_meter: Optional[float] = None
    altitude_change_meter: Optional[float] = None
    zone_duration: Optional[dict] = None


class Workout(BaseModel):
    id: str
    cycle_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime
    timezone_offset: str
    sport_id: int
    score_state: str
    score: Optional[WorkoutScore] = None


# ========== Summary Models ==========

class SleepSummary(BaseModel):
    date: str
    total_sleep_hours: float
    efficiency_percentage: float
    performance_percentage: float
    rem_hours: float
    deep_sleep_hours: float


class RecoverySummary(BaseModel):
    date: str
    recovery_score: Optional[float]
    hrv_milli: Optional[float]
    resting_heart_rate: Optional[float]


class WorkoutSummary(BaseModel):
    date: str
    sport_id: int
    strain: Optional[float]
    duration_minutes: float
    calories: Optional[float]


class HealthSummary(BaseModel):
    profile: UserProfile
    body_measurements: BodyMeasurements
    date_range_start: datetime
    date_range_end: datetime
    total_cycles: int
    total_recovery_records: int
    total_sleep_records: int
    total_workouts: int
    recent_recovery: list[RecoverySummary]
    recent_sleep: list[SleepSummary]
    recent_workouts: list[WorkoutSummary]


# ========== API Response Models ==========

class AuthStatus(BaseModel):
    authenticated: bool
    message: str


class DateRangeParams(BaseModel):
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    days: int = Field(7, description="Number of days to fetch (used if dates not specified)", ge=1, le=365)
