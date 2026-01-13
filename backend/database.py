"""
Database module for WHOOP health data storage.

Uses SQLite for local persistence - no server required.
"""

import sqlite3
from datetime import datetime, date
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

# Database file location
DB_PATH = Path(__file__).parent / "health_data.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialize database with all required tables."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                whoop_user_id INTEGER UNIQUE NOT NULL,
                email TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Body measurements table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS body_measurements (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                height_meter REAL,
                weight_kilogram REAL,
                max_heart_rate INTEGER,
                recorded_at DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, recorded_at)
            )
        """)

        # Cycles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cycles (
                id INTEGER PRIMARY KEY,
                whoop_cycle_id INTEGER UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                timezone_offset TEXT,
                score_state TEXT,
                strain REAL,
                kilojoule REAL,
                average_heart_rate INTEGER,
                max_heart_rate INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Recovery table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recovery (
                id INTEGER PRIMARY KEY,
                whoop_cycle_id INTEGER NOT NULL,
                whoop_sleep_id TEXT,
                user_id INTEGER NOT NULL,
                recorded_date DATE NOT NULL,
                score_state TEXT,
                recovery_score REAL,
                resting_heart_rate REAL,
                hrv_rmssd_milli REAL,
                spo2_percentage REAL,
                skin_temp_celsius REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, recorded_date)
            )
        """)

        # Sleep table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sleep (
                id INTEGER PRIMARY KEY,
                whoop_sleep_id TEXT UNIQUE NOT NULL,
                whoop_cycle_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                timezone_offset TEXT,
                is_nap BOOLEAN DEFAULT FALSE,
                score_state TEXT,
                total_in_bed_milli INTEGER,
                total_awake_milli INTEGER,
                total_light_sleep_milli INTEGER,
                total_slow_wave_sleep_milli INTEGER,
                total_rem_sleep_milli INTEGER,
                sleep_cycle_count INTEGER,
                disturbance_count INTEGER,
                respiratory_rate REAL,
                sleep_performance_percentage REAL,
                sleep_consistency_percentage REAL,
                sleep_efficiency_percentage REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Workouts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY,
                whoop_workout_id TEXT UNIQUE NOT NULL,
                whoop_cycle_id INTEGER,
                user_id INTEGER NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                timezone_offset TEXT,
                sport_id INTEGER,
                score_state TEXT,
                strain REAL,
                average_heart_rate INTEGER,
                max_heart_rate INTEGER,
                kilojoule REAL,
                distance_meter REAL,
                altitude_gain_meter REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Sync log table - tracks what data has been synced
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY,
                sync_date DATE NOT NULL,
                sync_type TEXT NOT NULL,
                status TEXT NOT NULL,
                records_synced INTEGER DEFAULT 0,
                error_message TEXT,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                UNIQUE(sync_date, sync_type)
            )
        """)

        # Create indexes for better query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recovery_date ON recovery(recorded_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sleep_start ON sleep(start_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workouts_start ON workouts(start_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cycles_start ON cycles(start_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_log_date ON sync_log(sync_date)")

        print(f"Database initialized at {DB_PATH}")


class HealthDataRepository:
    """Repository for health data CRUD operations."""

    def get_or_create_user(self, whoop_user_id: int, email: str = None,
                           first_name: str = None, last_name: str = None) -> int:
        """Get existing user or create new one. Returns user ID."""
        with get_db() as conn:
            cursor = conn.cursor()

            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE whoop_user_id = ?", (whoop_user_id,))
            row = cursor.fetchone()

            if row:
                # Update user info
                cursor.execute("""
                    UPDATE users SET email = ?, first_name = ?, last_name = ?, updated_at = ?
                    WHERE whoop_user_id = ?
                """, (email, first_name, last_name, datetime.now(), whoop_user_id))
                return row['id']
            else:
                # Create new user
                cursor.execute("""
                    INSERT INTO users (whoop_user_id, email, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                """, (whoop_user_id, email, first_name, last_name))
                return cursor.lastrowid

    def upsert_body_measurements(self, user_id: int, height: float, weight: float,
                                  max_hr: int, recorded_date: date):
        """Insert or update body measurements."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO body_measurements (user_id, height_meter, weight_kilogram, max_heart_rate, recorded_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, recorded_at) DO UPDATE SET
                    height_meter = excluded.height_meter,
                    weight_kilogram = excluded.weight_kilogram,
                    max_heart_rate = excluded.max_heart_rate
            """, (user_id, height, weight, max_hr, recorded_date))

    def upsert_cycle(self, user_id: int, cycle_data: dict):
        """Insert or update a cycle record."""
        with get_db() as conn:
            cursor = conn.cursor()
            score = cycle_data.get('score', {}) or {}
            cursor.execute("""
                INSERT INTO cycles (whoop_cycle_id, user_id, start_time, end_time, timezone_offset,
                                   score_state, strain, kilojoule, average_heart_rate, max_heart_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(whoop_cycle_id) DO UPDATE SET
                    end_time = excluded.end_time,
                    score_state = excluded.score_state,
                    strain = excluded.strain,
                    kilojoule = excluded.kilojoule,
                    average_heart_rate = excluded.average_heart_rate,
                    max_heart_rate = excluded.max_heart_rate
            """, (
                cycle_data['id'],
                user_id,
                cycle_data['start'],
                cycle_data.get('end'),
                cycle_data.get('timezone_offset'),
                cycle_data.get('score_state'),
                score.get('strain'),
                score.get('kilojoule'),
                score.get('average_heart_rate'),
                score.get('max_heart_rate')
            ))

    def upsert_recovery(self, user_id: int, recovery_data: dict):
        """Insert or update a recovery record."""
        with get_db() as conn:
            cursor = conn.cursor()
            score = recovery_data.get('score', {}) or {}
            recorded_date = recovery_data['created_at'][:10]

            cursor.execute("""
                INSERT INTO recovery (whoop_cycle_id, whoop_sleep_id, user_id, recorded_date,
                                     score_state, recovery_score, resting_heart_rate, hrv_rmssd_milli,
                                     spo2_percentage, skin_temp_celsius)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, recorded_date) DO UPDATE SET
                    whoop_cycle_id = excluded.whoop_cycle_id,
                    whoop_sleep_id = excluded.whoop_sleep_id,
                    score_state = excluded.score_state,
                    recovery_score = excluded.recovery_score,
                    resting_heart_rate = excluded.resting_heart_rate,
                    hrv_rmssd_milli = excluded.hrv_rmssd_milli,
                    spo2_percentage = excluded.spo2_percentage,
                    skin_temp_celsius = excluded.skin_temp_celsius
            """, (
                recovery_data['cycle_id'],
                recovery_data.get('sleep_id'),
                user_id,
                recorded_date,
                recovery_data.get('score_state'),
                score.get('recovery_score'),
                score.get('resting_heart_rate'),
                score.get('hrv_rmssd_milli'),
                score.get('spo2_percentage'),
                score.get('skin_temp_celsius')
            ))

    def upsert_sleep(self, user_id: int, sleep_data: dict):
        """Insert or update a sleep record."""
        with get_db() as conn:
            cursor = conn.cursor()
            score = sleep_data.get('score', {}) or {}
            stage = score.get('stage_summary', {}) or {}

            cursor.execute("""
                INSERT INTO sleep (whoop_sleep_id, whoop_cycle_id, user_id, start_time, end_time,
                                  timezone_offset, is_nap, score_state, total_in_bed_milli,
                                  total_awake_milli, total_light_sleep_milli, total_slow_wave_sleep_milli,
                                  total_rem_sleep_milli, sleep_cycle_count, disturbance_count,
                                  respiratory_rate, sleep_performance_percentage,
                                  sleep_consistency_percentage, sleep_efficiency_percentage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(whoop_sleep_id) DO UPDATE SET
                    score_state = excluded.score_state,
                    total_in_bed_milli = excluded.total_in_bed_milli,
                    total_awake_milli = excluded.total_awake_milli,
                    total_light_sleep_milli = excluded.total_light_sleep_milli,
                    total_slow_wave_sleep_milli = excluded.total_slow_wave_sleep_milli,
                    total_rem_sleep_milli = excluded.total_rem_sleep_milli,
                    sleep_cycle_count = excluded.sleep_cycle_count,
                    disturbance_count = excluded.disturbance_count,
                    respiratory_rate = excluded.respiratory_rate,
                    sleep_performance_percentage = excluded.sleep_performance_percentage,
                    sleep_consistency_percentage = excluded.sleep_consistency_percentage,
                    sleep_efficiency_percentage = excluded.sleep_efficiency_percentage
            """, (
                sleep_data['id'],
                sleep_data['cycle_id'],
                user_id,
                sleep_data['start'],
                sleep_data['end'],
                sleep_data.get('timezone_offset'),
                sleep_data.get('nap', False),
                sleep_data.get('score_state'),
                stage.get('total_in_bed_time_milli'),
                stage.get('total_awake_time_milli'),
                stage.get('total_light_sleep_time_milli'),
                stage.get('total_slow_wave_sleep_time_milli'),
                stage.get('total_rem_sleep_time_milli'),
                stage.get('sleep_cycle_count'),
                stage.get('disturbance_count'),
                score.get('respiratory_rate'),
                score.get('sleep_performance_percentage'),
                score.get('sleep_consistency_percentage'),
                score.get('sleep_efficiency_percentage')
            ))

    def upsert_workout(self, user_id: int, workout_data: dict):
        """Insert or update a workout record."""
        with get_db() as conn:
            cursor = conn.cursor()
            score = workout_data.get('score', {}) or {}

            cursor.execute("""
                INSERT INTO workouts (whoop_workout_id, whoop_cycle_id, user_id, start_time, end_time,
                                     timezone_offset, sport_id, score_state, strain, average_heart_rate,
                                     max_heart_rate, kilojoule, distance_meter, altitude_gain_meter)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(whoop_workout_id) DO UPDATE SET
                    score_state = excluded.score_state,
                    strain = excluded.strain,
                    average_heart_rate = excluded.average_heart_rate,
                    max_heart_rate = excluded.max_heart_rate,
                    kilojoule = excluded.kilojoule,
                    distance_meter = excluded.distance_meter,
                    altitude_gain_meter = excluded.altitude_gain_meter
            """, (
                workout_data['id'],
                workout_data.get('cycle_id'),  # May not exist in v2 API
                user_id,
                workout_data['start'],
                workout_data['end'],
                workout_data.get('timezone_offset'),
                workout_data.get('sport_id'),
                workout_data.get('score_state'),
                score.get('strain'),
                score.get('average_heart_rate'),
                score.get('max_heart_rate'),
                score.get('kilojoule'),
                score.get('distance_meter'),
                score.get('altitude_gain_meter')
            ))

    def log_sync(self, sync_date: date, sync_type: str, status: str,
                 records_synced: int = 0, error_message: str = None,
                 started_at: datetime = None, completed_at: datetime = None):
        """Log a sync operation."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_log (sync_date, sync_type, status, records_synced,
                                     error_message, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sync_date, sync_type) DO UPDATE SET
                    status = excluded.status,
                    records_synced = excluded.records_synced,
                    error_message = excluded.error_message,
                    completed_at = excluded.completed_at
            """, (sync_date, sync_type, status, records_synced, error_message,
                  started_at or datetime.now(), completed_at))

    def get_missing_sync_dates(self, days_back: int = 30) -> List[date]:
        """Get dates that haven't been successfully synced."""
        with get_db() as conn:
            cursor = conn.cursor()

            # Get all dates that should have been synced
            cursor.execute("""
                SELECT DISTINCT DATE(recorded_date) as sync_date
                FROM recovery
                WHERE recorded_date >= DATE('now', ?)
            """, (f'-{days_back} days',))

            synced_dates = {row['sync_date'] for row in cursor.fetchall()}

            # Generate all dates in range
            from datetime import timedelta
            today = date.today()
            all_dates = set()
            for i in range(1, days_back + 1):  # Start from 1 to exclude today
                all_dates.add((today - timedelta(days=i)).isoformat())

            # Find missing dates
            missing = sorted(all_dates - synced_dates)
            return [date.fromisoformat(d) for d in missing]

    def get_last_sync_date(self) -> Optional[date]:
        """Get the most recent successful sync date."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(recorded_date) as last_date FROM recovery
            """)
            row = cursor.fetchone()
            if row and row['last_date']:
                return date.fromisoformat(row['last_date'])
            return None

    def get_sync_stats(self) -> dict:
        """Get sync statistics."""
        with get_db() as conn:
            cursor = conn.cursor()

            stats = {}

            cursor.execute("SELECT COUNT(*) as count FROM recovery")
            stats['total_recovery_records'] = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM sleep")
            stats['total_sleep_records'] = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM workouts")
            stats['total_workout_records'] = cursor.fetchone()['count']

            cursor.execute("SELECT MIN(recorded_date) as min_date, MAX(recorded_date) as max_date FROM recovery")
            row = cursor.fetchone()
            stats['date_range'] = {'start': row['min_date'], 'end': row['max_date']}

            cursor.execute("""
                SELECT COUNT(*) as count FROM sync_log
                WHERE status = 'failed' AND sync_date >= DATE('now', '-7 days')
            """)
            stats['recent_failures'] = cursor.fetchone()['count']

            return stats

    # ========== Query Methods for API ==========

    def get_user_profile(self, user_id: int = None) -> Optional[dict]:
        """Get user profile. If no user_id, returns first user."""
        with get_db() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            else:
                cursor.execute("SELECT * FROM users LIMIT 1")
            row = cursor.fetchone()
            if row:
                return {
                    'user_id': row['whoop_user_id'],
                    'email': row['email'],
                    'first_name': row['first_name'],
                    'last_name': row['last_name']
                }
            return None

    def get_body_measurements(self, user_id: int = None) -> Optional[dict]:
        """Get latest body measurements."""
        with get_db() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("""
                    SELECT * FROM body_measurements
                    WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 1
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT * FROM body_measurements ORDER BY recorded_at DESC LIMIT 1
                """)
            row = cursor.fetchone()
            if row:
                return {
                    'height_meter': row['height_meter'],
                    'weight_kilogram': row['weight_kilogram'],
                    'max_heart_rate': row['max_heart_rate']
                }
            return None

    def get_recovery_data(self, start_date: date, end_date: date) -> List[dict]:
        """Get recovery data for date range."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM recovery
                WHERE recorded_date >= ? AND recorded_date <= ?
                ORDER BY recorded_date DESC
            """, (start_date.isoformat(), end_date.isoformat()))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'cycle_id': row['whoop_cycle_id'],
                    'sleep_id': row['whoop_sleep_id'],
                    'user_id': row['user_id'],
                    'created_at': row['recorded_date'] + 'T00:00:00.000Z',
                    'updated_at': row['recorded_date'] + 'T00:00:00.000Z',
                    'score_state': row['score_state'],
                    'score': {
                        'user_calibrating': False,
                        'recovery_score': row['recovery_score'],
                        'resting_heart_rate': row['resting_heart_rate'],
                        'hrv_rmssd_milli': row['hrv_rmssd_milli'],
                        'spo2_percentage': row['spo2_percentage'],
                        'skin_temp_celsius': row['skin_temp_celsius']
                    }
                })
            return results

    def get_sleep_data(self, start_date: date, end_date: date) -> List[dict]:
        """Get sleep data for date range."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sleep
                WHERE DATE(start_time) >= ? AND DATE(start_time) <= ?
                ORDER BY start_time DESC
            """, (start_date.isoformat(), end_date.isoformat()))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['whoop_sleep_id'],
                    'cycle_id': row['whoop_cycle_id'],
                    'user_id': row['user_id'],
                    'created_at': row['created_at'],
                    'updated_at': row['created_at'],
                    'start': row['start_time'],
                    'end': row['end_time'],
                    'timezone_offset': row['timezone_offset'],
                    'nap': bool(row['is_nap']),
                    'score_state': row['score_state'],
                    'score': {
                        'stage_summary': {
                            'total_in_bed_time_milli': row['total_in_bed_milli'] or 0,
                            'total_awake_time_milli': row['total_awake_milli'] or 0,
                            'total_light_sleep_time_milli': row['total_light_sleep_milli'] or 0,
                            'total_slow_wave_sleep_time_milli': row['total_slow_wave_sleep_milli'] or 0,
                            'total_rem_sleep_time_milli': row['total_rem_sleep_milli'] or 0,
                            'sleep_cycle_count': row['sleep_cycle_count'] or 0,
                            'disturbance_count': row['disturbance_count'] or 0
                        },
                        'respiratory_rate': row['respiratory_rate'],
                        'sleep_performance_percentage': row['sleep_performance_percentage'],
                        'sleep_consistency_percentage': row['sleep_consistency_percentage'],
                        'sleep_efficiency_percentage': row['sleep_efficiency_percentage']
                    }
                })
            return results

    def get_workout_data(self, start_date: date, end_date: date) -> List[dict]:
        """Get workout data for date range."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM workouts
                WHERE DATE(start_time) >= ? AND DATE(start_time) <= ?
                ORDER BY start_time DESC
            """, (start_date.isoformat(), end_date.isoformat()))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['whoop_workout_id'],
                    'cycle_id': row['whoop_cycle_id'],
                    'user_id': row['user_id'],
                    'created_at': row['created_at'],
                    'updated_at': row['created_at'],
                    'start': row['start_time'],
                    'end': row['end_time'],
                    'timezone_offset': row['timezone_offset'],
                    'sport_id': row['sport_id'],
                    'score_state': row['score_state'],
                    'score': {
                        'strain': row['strain'],
                        'average_heart_rate': row['average_heart_rate'],
                        'max_heart_rate': row['max_heart_rate'],
                        'kilojoule': row['kilojoule'],
                        'distance_meter': row['distance_meter'],
                        'altitude_gain_meter': row['altitude_gain_meter']
                    }
                })
            return results

    def get_cycle_data(self, start_date: date, end_date: date) -> List[dict]:
        """Get cycle data for date range."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM cycles
                WHERE DATE(start_time) >= ? AND DATE(start_time) <= ?
                ORDER BY start_time DESC
            """, (start_date.isoformat(), end_date.isoformat()))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['whoop_cycle_id'],
                    'user_id': row['user_id'],
                    'created_at': row['created_at'],
                    'updated_at': row['created_at'],
                    'start': row['start_time'],
                    'end': row['end_time'],
                    'timezone_offset': row['timezone_offset'],
                    'score_state': row['score_state'],
                    'score': {
                        'strain': row['strain'],
                        'kilojoule': row['kilojoule'],
                        'average_heart_rate': row['average_heart_rate'],
                        'max_heart_rate': row['max_heart_rate']
                    }
                })
            return results

    def get_default_user_id(self) -> Optional[int]:
        """Get the default (first) user's internal ID."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users LIMIT 1")
            row = cursor.fetchone()
            return row['id'] if row else None


if __name__ == "__main__":
    init_database()
    print("Database setup complete!")
