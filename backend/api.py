"""
WHOOP Health Data API

A FastAPI application exposing WHOOP health data via REST endpoints.
Data is served from the local SQLite database for fast, offline access.

Run with: uvicorn api:app --reload
API docs available at: http://localhost:8000/docs
"""

import os
import urllib.parse
from datetime import datetime, timedelta, timezone, date
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from models import (
    AuthStatus,
    UserProfile,
    BodyMeasurements,
    Cycle,
    Recovery,
    Sleep,
    Workout,
    HealthSummary,
    RecoverySummary,
    SleepSummary,
    WorkoutSummary,
)
from database import HealthDataRepository, init_database
from whoop_client import WhoopClient

load_dotenv()

# Initialize database on startup
init_database()

# ========== App Configuration ==========

app = FastAPI(
    title="WHOOP Health Data API",
    description="""
    REST API for accessing WHOOP health and fitness data.

    **Data is served from local database for fast, offline access.**

    ## Features
    - OAuth2 authentication with WHOOP
    - Access recovery, sleep, workout, and cycle data
    - Get health summaries and trends
    - Works offline once data is synced

    ## Authentication
    1. Call `/auth/login` to initiate OAuth flow
    2. Complete authentication in browser
    3. Data is synced automatically via cron job
    """,
    version="2.0.0",
    contact={
        "name": "WHOOP Health API",
    },
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Repository instance
repo = HealthDataRepository()

# Global client instance (for auth only)
_client: Optional[WhoopClient] = None


def get_client() -> WhoopClient:
    """Get or create the WHOOP client (for authentication)."""
    global _client

    client_id = os.getenv("WHOOP_CLIENT_ID")
    client_secret = os.getenv("WHOOP_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET must be set in environment"
        )

    if _client is None:
        _client = WhoopClient(client_id, client_secret)

    return _client


def require_data() -> None:
    """Ensure data exists in database."""
    if repo.get_default_user_id() is None:
        raise HTTPException(
            status_code=404,
            detail="No data in database. Please authenticate and run sync first."
        )


def parse_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    days: int
) -> tuple[date, date]:
    """Parse date range from parameters."""
    end_d = date.today()
    start_d = end_d - timedelta(days=days)

    if end_date:
        try:
            end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")

    if start_date:
        try:
            start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")

    return start_d, end_d


# ========== Authentication Endpoints ==========

@app.get(
    "/auth/login",
    tags=["Authentication"],
    summary="Initiate OAuth login",
    response_class=RedirectResponse,
)
def auth_login():
    """
    Redirects to WHOOP OAuth login page.

    After successful authentication, you'll be redirected to /auth/callback.
    """
    client = get_client()

    params = {
        "client_id": client.client_id,
        "redirect_uri": "http://localhost:8000/auth/callback",
        "response_type": "code",
        "scope": "offline read:profile read:body_measurement read:cycles read:recovery read:sleep read:workout",
        "state": "whoop_api_auth",
    }

    auth_url = f"https://api.prod.whoop.com/oauth/oauth2/auth?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get(
    "/auth/callback",
    tags=["Authentication"],
    summary="OAuth callback handler",
    response_model=AuthStatus,
)
def auth_callback(code: str = Query(..., description="Authorization code from WHOOP")):
    """
    Handles the OAuth callback from WHOOP.

    This endpoint is called automatically after successful login.
    """
    client = get_client()

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://localhost:8000/auth/callback",
        "client_id": client.client_id,
        "client_secret": client.client_secret,
    }

    try:
        response = requests.post(
            "https://api.prod.whoop.com/oauth/oauth2/token",
            data=data
        )
        response.raise_for_status()

        token_data = response.json()

        from whoop_client import WhoopTokens
        client.tokens = WhoopTokens(
            access_token=token_data["access_token"],
            expires_at=datetime.now() + timedelta(seconds=token_data["expires_in"] - 60),
            refresh_token=token_data.get("refresh_token"),
        )
        client._save_tokens()

        return AuthStatus(authenticated=True, message="Authentication successful! Run sync to load data.")

    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


@app.get(
    "/auth/status",
    tags=["Authentication"],
    summary="Check authentication status",
    response_model=AuthStatus,
)
def auth_status():
    """Check if the API has data available."""
    has_data = repo.get_default_user_id() is not None
    stats = repo.get_sync_stats() if has_data else None

    if has_data:
        return AuthStatus(
            authenticated=True,
            message=f"Data available: {stats['total_recovery_records']} recovery records from {stats['date_range']['start']} to {stats['date_range']['end']}"
        )
    else:
        return AuthStatus(authenticated=False, message="No data in database. Please authenticate and sync.")


@app.post(
    "/auth/logout",
    tags=["Authentication"],
    summary="Clear authentication",
    response_model=AuthStatus,
)
def auth_logout():
    """Clear stored authentication tokens."""
    global _client

    if os.path.exists(".whoop_token.json"):
        os.remove(".whoop_token.json")

    _client = None

    return AuthStatus(authenticated=False, message="Logged out successfully")


# ========== User Endpoints ==========

@app.get(
    "/profile",
    tags=["User"],
    summary="Get user profile",
    response_model=UserProfile,
)
def get_profile():
    """Get the user's profile information from local database."""
    require_data()

    data = repo.get_user_profile()
    if not data:
        raise HTTPException(status_code=404, detail="Profile not found")

    return UserProfile(**data)


@app.get(
    "/body",
    tags=["User"],
    summary="Get body measurements",
    response_model=BodyMeasurements,
)
def get_body_measurements():
    """Get body measurements including height, weight, and max heart rate."""
    require_data()

    data = repo.get_body_measurements()
    if not data:
        raise HTTPException(status_code=404, detail="Body measurements not found")

    return BodyMeasurements(**data)


# ========== Health Data Endpoints ==========

@app.get(
    "/cycles",
    tags=["Health Data"],
    summary="Get physiological cycles",
    response_model=list[Cycle],
)
def get_cycles(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    days: int = Query(7, description="Days to fetch if dates not specified", ge=1, le=365),
):
    """
    Get physiological cycles (daily periods from wake to wake).

    Each cycle includes strain score, kilojoules burned, and heart rate data.
    """
    require_data()
    start_d, end_d = parse_date_range(start_date, end_date, days)

    data = repo.get_cycle_data(start_d, end_d)
    return [Cycle(**c) for c in data]


@app.get(
    "/recovery",
    tags=["Health Data"],
    summary="Get recovery data",
    response_model=list[Recovery],
)
def get_recovery(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    days: int = Query(7, description="Days to fetch if dates not specified", ge=1, le=365),
):
    """
    Get recovery data including recovery score, HRV, and resting heart rate.

    Recovery is calculated after each sleep and indicates readiness for strain.
    """
    require_data()
    start_d, end_d = parse_date_range(start_date, end_date, days)

    data = repo.get_recovery_data(start_d, end_d)
    return [Recovery(**r) for r in data]


@app.get(
    "/sleep",
    tags=["Health Data"],
    summary="Get sleep data",
    response_model=list[Sleep],
)
def get_sleep(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    days: int = Query(7, description="Days to fetch if dates not specified", ge=1, le=365),
):
    """
    Get sleep data including duration, stages, and quality metrics.

    Includes REM, deep sleep, light sleep durations and efficiency scores.
    """
    require_data()
    start_d, end_d = parse_date_range(start_date, end_date, days)

    data = repo.get_sleep_data(start_d, end_d)
    return [Sleep(**s) for s in data]


@app.get(
    "/workouts",
    tags=["Health Data"],
    summary="Get workout data",
    response_model=list[Workout],
)
def get_workouts(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    days: int = Query(7, description="Days to fetch if dates not specified", ge=1, le=365),
):
    """
    Get workout data including strain, heart rate, and activity details.

    Each workout includes sport type, duration, and performance metrics.
    """
    require_data()
    start_d, end_d = parse_date_range(start_date, end_date, days)

    data = repo.get_workout_data(start_d, end_d)
    return [Workout(**w) for w in data]


# ========== Summary Endpoint ==========

@app.get(
    "/summary",
    tags=["Health Data"],
    summary="Get health summary",
    response_model=HealthSummary,
)
def get_summary(
    days: int = Query(7, description="Number of days to summarize", ge=1, le=365),
):
    """
    Get a comprehensive health summary including recent recovery, sleep, and workouts.

    This is a convenience endpoint that aggregates data from multiple sources.
    Data is served from local database for fast access.
    """
    require_data()

    end_d = date.today()
    start_d = end_d - timedelta(days=days)

    # Fetch all data from database
    profile = repo.get_user_profile()
    body = repo.get_body_measurements()
    cycles = repo.get_cycle_data(start_d, end_d)
    recovery_data = repo.get_recovery_data(start_d, end_d)
    sleep_data = repo.get_sleep_data(start_d, end_d)
    workout_data = repo.get_workout_data(start_d, end_d)

    # Build recovery summaries
    recent_recovery = []
    for rec in recovery_data:
        score = rec.get("score", {})
        recent_recovery.append(RecoverySummary(
            date=rec.get("created_at", "")[:10],
            recovery_score=score.get("recovery_score"),
            hrv_milli=score.get("hrv_rmssd_milli"),
            resting_heart_rate=score.get("resting_heart_rate"),
        ))

    # Build sleep summaries
    recent_sleep = []
    for sleep in sleep_data:
        score = sleep.get("score", {})
        stage = score.get("stage_summary", {})

        total_sleep_ms = (
            stage.get("total_light_sleep_time_milli", 0) +
            stage.get("total_slow_wave_sleep_time_milli", 0) +
            stage.get("total_rem_sleep_time_milli", 0)
        )

        recent_sleep.append(SleepSummary(
            date=sleep.get("start", "")[:10],
            total_sleep_hours=total_sleep_ms / 3600000,
            efficiency_percentage=score.get("sleep_efficiency_percentage", 0) or 0,
            performance_percentage=score.get("sleep_performance_percentage", 0) or 0,
            rem_hours=stage.get("total_rem_sleep_time_milli", 0) / 3600000,
            deep_sleep_hours=stage.get("total_slow_wave_sleep_time_milli", 0) / 3600000,
        ))

    # Build workout summaries
    recent_workouts = []
    for workout in workout_data:
        score = workout.get("score", {})
        try:
            start_time = datetime.fromisoformat(workout["start"].replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(workout["end"].replace("Z", "+00:00"))
            duration = (end_time - start_time).total_seconds() / 60
        except:
            duration = 0

        recent_workouts.append(WorkoutSummary(
            date=workout.get("start", "")[:10],
            sport_id=workout.get("sport_id", 0) or 0,
            strain=score.get("strain"),
            duration_minutes=duration,
            calories=score.get("kilojoule", 0) / 4.184 if score.get("kilojoule") else None,
        ))

    return HealthSummary(
        profile=UserProfile(**profile),
        body_measurements=BodyMeasurements(**body),
        date_range_start=datetime.combine(start_d, datetime.min.time()).replace(tzinfo=timezone.utc),
        date_range_end=datetime.combine(end_d, datetime.max.time()).replace(tzinfo=timezone.utc),
        total_cycles=len(cycles),
        total_recovery_records=len(recovery_data),
        total_sleep_records=len(sleep_data),
        total_workouts=len(workout_data),
        recent_recovery=recent_recovery,
        recent_sleep=recent_sleep,
        recent_workouts=recent_workouts,
    )


# ========== Sync Endpoint ==========

@app.post(
    "/sync",
    tags=["System"],
    summary="Trigger data sync",
)
def trigger_sync(
    days: int = Query(7, description="Number of days to sync", ge=1, le=365),
):
    """
    Manually trigger a data sync from WHOOP API to local database.

    This fetches fresh data from WHOOP and stores it locally.
    """
    try:
        from sync_service import SyncService
        sync = SyncService()
        stats = sync.full_sync(days=days)

        return {
            "status": "success",
            "synced": {
                "cycles": stats["cycles"],
                "recovery": stats["recovery"],
                "sleep": stats["sleep"],
                "workouts": stats["workouts"],
            },
            "errors": stats.get("errors", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Health Check ==========

@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
)
def health_check():
    """Check if the API is running."""
    stats = repo.get_sync_stats()
    return {
        "status": "healthy",
        "service": "whoop-health-api",
        "database": {
            "recovery_records": stats["total_recovery_records"],
            "sleep_records": stats["total_sleep_records"],
            "workout_records": stats["total_workout_records"],
            "date_range": stats["date_range"]
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
