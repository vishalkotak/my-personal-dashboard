"""
Example usage of the WHOOP client.

This script demonstrates various ways to fetch and analyze your WHOOP health data.
"""

import os
from datetime import datetime, timedelta, timezone
from whoop_client import WhoopClient
from dotenv import load_dotenv

load_dotenv()


def analyze_recovery_trends(client: WhoopClient, days: int = 30):
    """Analyze recovery trends over the past N days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    print(f"\n{'='*50}")
    print(f"RECOVERY ANALYSIS (Last {days} days)")
    print('='*50)

    recovery_data = client.get_recovery(start, end)

    if not recovery_data:
        print("No recovery data found.")
        return

    scores = []
    hrvs = []
    rhrs = []

    for rec in recovery_data:
        score = rec.get("score", {})
        if score.get("recovery_score") is not None:
            scores.append(score["recovery_score"])
        if score.get("hrv_rmssd_milli") is not None:
            hrvs.append(score["hrv_rmssd_milli"])
        if score.get("resting_heart_rate") is not None:
            rhrs.append(score["resting_heart_rate"])

    if scores:
        print(f"\nRecovery Score:")
        print(f"  Average: {sum(scores)/len(scores):.1f}%")
        print(f"  Best: {max(scores)}%")
        print(f"  Lowest: {min(scores)}%")

    if hrvs:
        print(f"\nHeart Rate Variability (HRV):")
        print(f"  Average: {sum(hrvs)/len(hrvs):.1f} ms")
        print(f"  Best: {max(hrvs):.1f} ms")
        print(f"  Lowest: {min(hrvs):.1f} ms")

    if rhrs:
        print(f"\nResting Heart Rate:")
        print(f"  Average: {sum(rhrs)/len(rhrs):.1f} bpm")
        print(f"  Best (lowest): {min(rhrs)} bpm")
        print(f"  Highest: {max(rhrs)} bpm")


def analyze_sleep_quality(client: WhoopClient, days: int = 14):
    """Analyze sleep patterns over the past N days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    print(f"\n{'='*50}")
    print(f"SLEEP ANALYSIS (Last {days} days)")
    print('='*50)

    sleep_data = client.get_sleep(start, end)

    if not sleep_data:
        print("No sleep data found.")
        return

    total_durations = []
    efficiencies = []
    rem_durations = []
    deep_durations = []

    for sleep in sleep_data:
        score = sleep.get("score", {})
        stage = score.get("stage_summary", {})

        # Calculate total sleep (light + deep + REM)
        total_ms = (
            stage.get("total_light_sleep_time_milli", 0) +
            stage.get("total_slow_wave_sleep_time_milli", 0) +
            stage.get("total_rem_sleep_time_milli", 0)
        )
        if total_ms > 0:
            total_durations.append(total_ms / 3600000)  # Convert to hours

        if score.get("sleep_efficiency_percentage"):
            efficiencies.append(score["sleep_efficiency_percentage"])

        if stage.get("total_rem_sleep_time_milli"):
            rem_durations.append(stage["total_rem_sleep_time_milli"] / 3600000)

        if stage.get("total_slow_wave_sleep_time_milli"):
            deep_durations.append(stage["total_slow_wave_sleep_time_milli"] / 3600000)

    if total_durations:
        print(f"\nTotal Sleep Duration:")
        print(f"  Average: {sum(total_durations)/len(total_durations):.1f} hours")
        print(f"  Best: {max(total_durations):.1f} hours")
        print(f"  Shortest: {min(total_durations):.1f} hours")

    if efficiencies:
        print(f"\nSleep Efficiency:")
        print(f"  Average: {sum(efficiencies)/len(efficiencies):.1f}%")

    if rem_durations:
        print(f"\nREM Sleep:")
        print(f"  Average: {sum(rem_durations)/len(rem_durations)*60:.0f} min")

    if deep_durations:
        print(f"\nDeep Sleep (Slow Wave):")
        print(f"  Average: {sum(deep_durations)/len(deep_durations)*60:.0f} min")


def analyze_workouts(client: WhoopClient, days: int = 30):
    """Analyze workout data over the past N days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    print(f"\n{'='*50}")
    print(f"WORKOUT ANALYSIS (Last {days} days)")
    print('='*50)

    workouts = client.get_workouts(start, end)

    if not workouts:
        print("No workout data found.")
        return

    print(f"\nTotal Workouts: {len(workouts)}")

    # Group by sport type
    sport_counts = {}
    strains = []

    for workout in workouts:
        sport_id = workout.get("sport_id", 0)
        sport_counts[sport_id] = sport_counts.get(sport_id, 0) + 1

        score = workout.get("score", {})
        if score.get("strain"):
            strains.append(score["strain"])

    if strains:
        print(f"\nStrain Scores:")
        print(f"  Average: {sum(strains)/len(strains):.1f}")
        print(f"  Highest: {max(strains):.1f}")

    print(f"\nWorkouts per Sport ID:")
    for sport_id, count in sorted(sport_counts.items(), key=lambda x: -x[1]):
        print(f"  Sport {sport_id}: {count} workouts")


def get_today_summary(client: WhoopClient):
    """Get today's health summary."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=1)

    print(f"\n{'='*50}")
    print("TODAY'S SUMMARY")
    print('='*50)

    # Get latest recovery
    recovery = client.get_recovery(start, end)
    if recovery:
        latest = recovery[-1]
        score = latest.get("score", {})
        print(f"\nRecovery Score: {score.get('recovery_score', 'N/A')}%")
        print(f"HRV: {score.get('hrv_rmssd_milli', 'N/A')} ms")
        print(f"Resting Heart Rate: {score.get('resting_heart_rate', 'N/A')} bpm")

    # Get last night's sleep
    sleep = client.get_sleep(start, end)
    if sleep:
        latest = sleep[-1]
        score = latest.get("score", {})
        total_hours = score.get("total_sleep_duration_milli", 0) / 3600000
        print(f"\nLast Night's Sleep: {total_hours:.1f} hours")
        print(f"Sleep Efficiency: {score.get('sleep_efficiency_percentage', 'N/A')}%")

    # Get today's workouts
    workouts = client.get_workouts(start, end)
    print(f"\nWorkouts Today: {len(workouts)}")


def main():
    client_id = os.getenv("WHOOP_CLIENT_ID")
    client_secret = os.getenv("WHOOP_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Please set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET in .env file")
        return

    client = WhoopClient(client_id, client_secret)
    client.authenticate()

    # Run different analyses
    get_today_summary(client)
    analyze_recovery_trends(client, days=30)
    analyze_sleep_quality(client, days=14)
    analyze_workouts(client, days=30)


if __name__ == "__main__":
    main()
