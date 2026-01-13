"""
Database module for WHOOP health data storage.

Uses SQLite for local persistence - no server required.
"""

import sqlite3
from datetime import datetime, date, timedelta
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

        # ========== Hypertrophy Tracking Tables ==========

        # Exercise definitions - catalog of exercises
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                muscle_group TEXT NOT NULL,
                equipment TEXT,
                is_compound BOOLEAN DEFAULT FALSE,
                baseline_weight REAL,
                notes TEXT
            )
        """)

        # Workout program templates (Upper A, Lower A, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workout_templates (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                day_type TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER DEFAULT 0
            )
        """)

        # Exercises assigned to each workout template
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS template_exercises (
                id INTEGER PRIMARY KEY,
                template_id INTEGER NOT NULL,
                exercise_id INTEGER NOT NULL,
                sort_order INTEGER DEFAULT 0,
                target_sets INTEGER DEFAULT 3,
                target_reps_min INTEGER DEFAULT 6,
                target_reps_max INTEGER DEFAULT 10,
                target_rir INTEGER DEFAULT 2,
                rest_seconds INTEGER DEFAULT 150,
                notes TEXT,
                FOREIGN KEY (template_id) REFERENCES workout_templates(id),
                FOREIGN KEY (exercise_id) REFERENCES exercises(id),
                UNIQUE(template_id, exercise_id)
            )
        """)

        # Gym sessions - each workout logged
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gym_sessions (
                id INTEGER PRIMARY KEY,
                template_id INTEGER,
                session_date DATE NOT NULL,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (template_id) REFERENCES workout_templates(id)
            )
        """)

        # Individual exercise sets logged
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exercise_sets (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL,
                exercise_id INTEGER NOT NULL,
                set_number INTEGER NOT NULL,
                weight_lbs REAL,
                reps INTEGER,
                rir INTEGER,
                is_warmup BOOLEAN DEFAULT FALSE,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES gym_sessions(id),
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            )
        """)

        # Personal records tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personal_records (
                id INTEGER PRIMARY KEY,
                exercise_id INTEGER NOT NULL,
                weight_lbs REAL NOT NULL,
                reps INTEGER NOT NULL,
                estimated_1rm REAL,
                achieved_date DATE NOT NULL,
                session_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id),
                FOREIGN KEY (session_id) REFERENCES gym_sessions(id)
            )
        """)

        # Indexes for hypertrophy tables
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gym_sessions_date ON gym_sessions(session_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exercise_sets_session ON exercise_sets(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_personal_records_exercise ON personal_records(exercise_id)")

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


class HypertrophyRepository:
    """Repository for hypertrophy/workout tracking CRUD operations."""

    # ========== Exercise Management ==========

    def create_exercise(self, name: str, muscle_group: str, equipment: str = None,
                       is_compound: bool = False, baseline_weight: float = None,
                       notes: str = None) -> int:
        """Create a new exercise definition."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO exercises (name, muscle_group, equipment, is_compound, baseline_weight, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, muscle_group, equipment, is_compound, baseline_weight, notes))
            return cursor.lastrowid

    def get_all_exercises(self) -> List[dict]:
        """Get all exercise definitions."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM exercises ORDER BY muscle_group, name")
            return [dict(row) for row in cursor.fetchall()]

    def get_exercises_by_muscle_group(self, muscle_group: str) -> List[dict]:
        """Get exercises for a specific muscle group."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM exercises WHERE muscle_group = ? ORDER BY name",
                (muscle_group,)
            )
            return [dict(row) for row in cursor.fetchall()]

    # ========== Workout Template Management ==========

    def create_workout_template(self, name: str, day_type: str,
                                description: str = None, sort_order: int = 0) -> int:
        """Create a workout template (e.g., Upper A, Lower B)."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO workout_templates (name, day_type, description, sort_order)
                VALUES (?, ?, ?, ?)
            """, (name, day_type, description, sort_order))
            return cursor.lastrowid

    def get_all_templates(self) -> List[dict]:
        """Get all workout templates."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workout_templates ORDER BY sort_order")
            return [dict(row) for row in cursor.fetchall()]

    def get_template_with_exercises(self, template_id: int) -> dict:
        """Get a workout template with all its exercises."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workout_templates WHERE id = ?", (template_id,))
            template = cursor.fetchone()
            if not template:
                return None

            result = dict(template)
            cursor.execute("""
                SELECT te.*, e.name, e.muscle_group, e.equipment, e.is_compound
                FROM template_exercises te
                JOIN exercises e ON te.exercise_id = e.id
                WHERE te.template_id = ?
                ORDER BY te.sort_order
            """, (template_id,))
            result['exercises'] = [dict(row) for row in cursor.fetchall()]
            return result

    def add_exercise_to_template(self, template_id: int, exercise_id: int,
                                  sort_order: int = 0, target_sets: int = 3,
                                  target_reps_min: int = 6, target_reps_max: int = 10,
                                  target_rir: int = 2, rest_seconds: int = 150,
                                  notes: str = None) -> int:
        """Add an exercise to a workout template."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO template_exercises
                (template_id, exercise_id, sort_order, target_sets, target_reps_min,
                 target_reps_max, target_rir, rest_seconds, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (template_id, exercise_id, sort_order, target_sets, target_reps_min,
                  target_reps_max, target_rir, rest_seconds, notes))
            return cursor.lastrowid

    # ========== Gym Session Management ==========

    def create_session(self, template_id: int, session_date: date,
                       started_at: datetime = None, notes: str = None) -> int:
        """Create a new gym session."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO gym_sessions (template_id, session_date, started_at, notes)
                VALUES (?, ?, ?, ?)
            """, (template_id, session_date.isoformat(), started_at, notes))
            return cursor.lastrowid

    def complete_session(self, session_id: int, completed_at: datetime = None):
        """Mark a session as completed."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE gym_sessions SET completed_at = ?
                WHERE id = ?
            """, (completed_at or datetime.now(), session_id))

    def get_session(self, session_id: int) -> dict:
        """Get a session with all its logged sets."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT gs.*, wt.name as template_name, wt.day_type
                FROM gym_sessions gs
                LEFT JOIN workout_templates wt ON gs.template_id = wt.id
                WHERE gs.id = ?
            """, (session_id,))
            session = cursor.fetchone()
            if not session:
                return None

            result = dict(session)
            cursor.execute("""
                SELECT es.*, e.name as exercise_name, e.muscle_group, e.equipment
                FROM exercise_sets es
                JOIN exercises e ON es.exercise_id = e.id
                WHERE es.session_id = ?
                ORDER BY e.id, es.set_number
            """, (session_id,))
            result['sets'] = [dict(row) for row in cursor.fetchall()]
            return result

    def get_sessions_by_date_range(self, start_date: date, end_date: date) -> List[dict]:
        """Get all sessions within a date range."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT gs.*, wt.name as template_name, wt.day_type,
                       COUNT(DISTINCT es.id) as total_sets
                FROM gym_sessions gs
                LEFT JOIN workout_templates wt ON gs.template_id = wt.id
                LEFT JOIN exercise_sets es ON gs.id = es.session_id AND es.is_warmup = 0
                WHERE gs.session_date >= ? AND gs.session_date <= ?
                GROUP BY gs.id
                ORDER BY gs.session_date DESC
            """, (start_date.isoformat(), end_date.isoformat()))
            return [dict(row) for row in cursor.fetchall()]

    def get_recent_sessions(self, limit: int = 10) -> List[dict]:
        """Get most recent gym sessions."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT gs.*, wt.name as template_name, wt.day_type,
                       COUNT(DISTINCT es.id) as total_sets
                FROM gym_sessions gs
                LEFT JOIN workout_templates wt ON gs.template_id = wt.id
                LEFT JOIN exercise_sets es ON gs.id = es.session_id AND es.is_warmup = 0
                GROUP BY gs.id
                ORDER BY gs.session_date DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # ========== Exercise Set Logging ==========

    def log_set(self, session_id: int, exercise_id: int, set_number: int,
                weight_lbs: float, reps: int, rir: int = None,
                is_warmup: bool = False, notes: str = None) -> int:
        """Log a single set for an exercise."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO exercise_sets
                (session_id, exercise_id, set_number, weight_lbs, reps, rir, is_warmup, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, exercise_id, set_number, weight_lbs, reps, rir, is_warmup, notes))
            return cursor.lastrowid

    def update_set(self, set_id: int, weight_lbs: float = None, reps: int = None,
                   rir: int = None, notes: str = None):
        """Update an existing set."""
        with get_db() as conn:
            cursor = conn.cursor()
            updates = []
            values = []
            if weight_lbs is not None:
                updates.append("weight_lbs = ?")
                values.append(weight_lbs)
            if reps is not None:
                updates.append("reps = ?")
                values.append(reps)
            if rir is not None:
                updates.append("rir = ?")
                values.append(rir)
            if notes is not None:
                updates.append("notes = ?")
                values.append(notes)

            if updates:
                values.append(set_id)
                cursor.execute(f"""
                    UPDATE exercise_sets SET {', '.join(updates)}
                    WHERE id = ?
                """, values)

    def delete_set(self, set_id: int):
        """Delete a set."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM exercise_sets WHERE id = ?", (set_id,))

    def get_sets_for_exercise_in_session(self, session_id: int, exercise_id: int) -> List[dict]:
        """Get all sets for a specific exercise in a session."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM exercise_sets
                WHERE session_id = ? AND exercise_id = ?
                ORDER BY set_number
            """, (session_id, exercise_id))
            return [dict(row) for row in cursor.fetchall()]

    # ========== Progress & History ==========

    def get_exercise_history(self, exercise_id: int, limit: int = 20) -> List[dict]:
        """Get recent history for a specific exercise."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT gs.session_date, es.set_number, es.weight_lbs, es.reps, es.rir
                FROM exercise_sets es
                JOIN gym_sessions gs ON es.session_id = gs.id
                WHERE es.exercise_id = ? AND es.is_warmup = 0
                ORDER BY gs.session_date DESC, es.set_number
                LIMIT ?
            """, (exercise_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_last_workout_for_exercise(self, exercise_id: int) -> List[dict]:
        """Get the last workout data for an exercise (for suggesting weights)."""
        with get_db() as conn:
            cursor = conn.cursor()
            # Get the most recent session that included this exercise
            cursor.execute("""
                SELECT gs.id, gs.session_date
                FROM gym_sessions gs
                JOIN exercise_sets es ON gs.id = es.session_id
                WHERE es.exercise_id = ? AND es.is_warmup = 0
                ORDER BY gs.session_date DESC
                LIMIT 1
            """, (exercise_id,))
            last_session = cursor.fetchone()
            if not last_session:
                return []

            cursor.execute("""
                SELECT set_number, weight_lbs, reps, rir
                FROM exercise_sets
                WHERE session_id = ? AND exercise_id = ? AND is_warmup = 0
                ORDER BY set_number
            """, (last_session['id'], exercise_id))
            return [dict(row) for row in cursor.fetchall()]

    def calculate_estimated_1rm(self, weight: float, reps: int) -> float:
        """Calculate estimated 1RM using Brzycki formula."""
        if reps >= 37:  # Formula becomes unreliable
            return weight
        return weight * (36 / (37 - reps))

    def save_personal_record(self, exercise_id: int, weight_lbs: float, reps: int,
                             achieved_date: date, session_id: int = None) -> int:
        """Save a new personal record."""
        estimated_1rm = self.calculate_estimated_1rm(weight_lbs, reps)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO personal_records
                (exercise_id, weight_lbs, reps, estimated_1rm, achieved_date, session_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (exercise_id, weight_lbs, reps, estimated_1rm, achieved_date.isoformat(), session_id))
            return cursor.lastrowid

    def get_personal_records(self, exercise_id: int = None) -> List[dict]:
        """Get personal records, optionally filtered by exercise."""
        with get_db() as conn:
            cursor = conn.cursor()
            if exercise_id:
                cursor.execute("""
                    SELECT pr.*, e.name as exercise_name
                    FROM personal_records pr
                    JOIN exercises e ON pr.exercise_id = e.id
                    WHERE pr.exercise_id = ?
                    ORDER BY pr.estimated_1rm DESC
                """, (exercise_id,))
            else:
                cursor.execute("""
                    SELECT pr.*, e.name as exercise_name
                    FROM personal_records pr
                    JOIN exercises e ON pr.exercise_id = e.id
                    ORDER BY e.name, pr.estimated_1rm DESC
                """)
            return [dict(row) for row in cursor.fetchall()]

    # ========== Weight Suggestion Logic ==========

    def get_exercise_baseline(self, exercise_id: int) -> float:
        """Get baseline weight for an exercise."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT baseline_weight FROM exercises WHERE id = ?", (exercise_id,))
            row = cursor.fetchone()
            return row['baseline_weight'] if row and row['baseline_weight'] else None

    def suggest_weight(self, exercise_id: int, target_reps: int = 8) -> dict:
        """Suggest weight for next workout based on progressive overload."""
        last_workout = self.get_last_workout_for_exercise(exercise_id)

        if not last_workout:
            # No history - return baseline weight
            baseline = self.get_exercise_baseline(exercise_id)
            if baseline:
                return {
                    'suggestion': baseline,
                    'reason': 'Starting weight based on your profile',
                    'last_max': None,
                    'last_reps': None
                }
            return {'suggestion': None, 'reason': 'No previous data'}

        # Analyze last workout
        total_reps = sum(s['reps'] or 0 for s in last_workout)
        avg_weight = sum(s['weight_lbs'] or 0 for s in last_workout) / len(last_workout)
        avg_rir = sum(s['rir'] or 2 for s in last_workout) / len(last_workout)
        max_weight = max(s['weight_lbs'] or 0 for s in last_workout)

        # If hit top of rep range with good RIR, suggest weight increase
        if total_reps >= 10 * len(last_workout) and avg_rir <= 2:
            new_weight = max_weight + 5  # Increase by 5 lbs
            return {
                'suggestion': new_weight,
                'reason': 'Progressive overload - hit rep target',
                'last_max': max_weight,
                'last_reps': total_reps
            }
        else:
            return {
                'suggestion': max_weight,
                'reason': 'Maintain weight - build toward rep target',
                'last_max': max_weight,
                'last_reps': total_reps
            }

    # ========== Statistics ==========

    def get_volume_history(self, days: int = 30) -> List[dict]:
        """Get daily volume history for charting."""
        with get_db() as conn:
            cursor = conn.cursor()
            start_date = (date.today() - timedelta(days=days)).isoformat()

            cursor.execute("""
                SELECT
                    gs.session_date,
                    wt.name as workout_name,
                    SUM(es.weight_lbs * es.reps) as volume
                FROM gym_sessions gs
                LEFT JOIN workout_templates wt ON gs.template_id = wt.id
                LEFT JOIN exercise_sets es ON gs.id = es.session_id AND es.is_warmup = 0
                WHERE gs.session_date >= ?
                GROUP BY gs.session_date
                ORDER BY gs.session_date
            """, (start_date,))

            return [dict(row) for row in cursor.fetchall()]

    def get_workout_stats(self, days: int = 30) -> dict:
        """Get workout statistics for the past N days."""
        with get_db() as conn:
            cursor = conn.cursor()
            start_date = (date.today() - timedelta(days=days)).isoformat()

            cursor.execute("""
                SELECT COUNT(*) as total_sessions
                FROM gym_sessions
                WHERE session_date >= ?
            """, (start_date,))
            total_sessions = cursor.fetchone()['total_sessions']

            cursor.execute("""
                SELECT COUNT(*) as total_sets
                FROM exercise_sets es
                JOIN gym_sessions gs ON es.session_id = gs.id
                WHERE gs.session_date >= ? AND es.is_warmup = 0
            """, (start_date,))
            total_sets = cursor.fetchone()['total_sets']

            cursor.execute("""
                SELECT SUM(es.weight_lbs * es.reps) as total_volume
                FROM exercise_sets es
                JOIN gym_sessions gs ON es.session_id = gs.id
                WHERE gs.session_date >= ? AND es.is_warmup = 0
            """, (start_date,))
            row = cursor.fetchone()
            total_volume = row['total_volume'] or 0

            cursor.execute("""
                SELECT e.muscle_group, COUNT(*) as set_count
                FROM exercise_sets es
                JOIN exercises e ON es.exercise_id = e.id
                JOIN gym_sessions gs ON es.session_id = gs.id
                WHERE gs.session_date >= ? AND es.is_warmup = 0
                GROUP BY e.muscle_group
            """, (start_date,))
            sets_by_muscle = {row['muscle_group']: row['set_count'] for row in cursor.fetchall()}

            return {
                'total_sessions': total_sessions,
                'total_sets': total_sets,
                'total_volume_lbs': total_volume,
                'sets_by_muscle_group': sets_by_muscle,
                'days_analyzed': days
            }


def seed_workout_program():
    """Seed the database with the trainer's workout program."""
    repo = HypertrophyRepository()

    # Check if already seeded
    if repo.get_all_exercises():
        print("Workout program already seeded")
        return

    print("Seeding workout program...")

    # Create exercises with baseline weights
    # Baselines calibrated for 6'4", 187 lbs male, beginner-intermediate
    # Machine weights are total stack weight
    # Dumbbell weights are per hand
    exercises = [
        # Chest - (name, muscle, equipment, is_compound, baseline_lbs)
        ("Converging Chest Press", "Chest", "Converging Chest Press Machine", True, 110),
        ("Dumbbell Bench Press", "Chest", "Bench + Dumbbells", True, 40),
        ("Dumbbell Incline Press", "Chest", "Bench + Dumbbells", True, 35),
        ("Cable Fly", "Chest", "Cable Machine", False, 25),

        # Shoulders
        ("Converging Shoulder Press", "Shoulders", "Converging Shoulder Press Machine", True, 90),
        ("Dumbbell Shoulder Press", "Shoulders", "Bench + Dumbbells", True, 30),
        ("Dumbbell Lateral Raise", "Shoulders", "Dumbbells", False, 15),
        ("Cable Lateral Raise", "Shoulders", "Cable Machine", False, 15),

        # Back
        ("Seated Row", "Back", "Seated Row Machine", True, 110),
        ("Lat Pulldown", "Back", "Lat Pulldown Machine", True, 110),
        ("Dumbbell Row", "Back", "Bench + Dumbbells", True, 40),

        # Biceps
        ("Cable Curl", "Biceps", "Cable Machine", False, 50),
        ("Dumbbell Curl", "Biceps", "Dumbbells", False, 25),
        ("Hammer Curl", "Biceps", "Dumbbells", False, 25),

        # Triceps
        ("Cable Tricep Pushdown", "Triceps", "Cable Machine", False, 60),
        ("Cable Overhead Tricep Extension", "Triceps", "Cable Machine", False, 50),
        ("Dumbbell Tricep Extension", "Triceps", "Dumbbells", False, 25),

        # Quads
        ("Leg Press", "Quads", "Leg Press Machine", True, 230),
        ("Leg Extension", "Quads", "Leg Extension Machine", False, 90),
        ("Dumbbell Lunge", "Quads", "Dumbbells", True, 30),

        # Hamstrings
        ("Leg Curl", "Hamstrings", "Leg Curl Machine", False, 80),
        ("Dumbbell RDL", "Hamstrings", "Dumbbells", True, 35),

        # Glutes
        ("Hip Thrust", "Glutes", "Bench + Dumbbells", True, 40),
    ]

    exercise_ids = {}
    for name, muscle, equipment, is_compound, baseline in exercises:
        eid = repo.create_exercise(name, muscle, equipment, is_compound, baseline)
        exercise_ids[name] = eid

    # Create workout templates (4-day Upper/Lower split)
    upper_a = repo.create_workout_template("Upper A", "upper", "Push focus - Chest & Triceps emphasis", 1)
    lower_a = repo.create_workout_template("Lower A", "lower", "Quad focus", 2)
    upper_b = repo.create_workout_template("Upper B", "upper", "Pull focus - Back & Biceps emphasis", 3)
    lower_b = repo.create_workout_template("Lower B", "lower", "Hamstring focus", 4)

    # Upper A - Push focus
    upper_a_exercises = [
        ("Converging Chest Press", 1, 3, 6, 10, 2, 180),
        ("Converging Shoulder Press", 2, 3, 6, 10, 2, 180),
        ("Seated Row", 3, 3, 6, 10, 2, 150),
        ("Dumbbell Lateral Raise", 4, 3, 10, 15, 2, 90),
        ("Cable Tricep Pushdown", 5, 3, 8, 12, 2, 90),
        ("Cable Curl", 6, 3, 8, 12, 2, 90),
    ]

    # Lower A - Quad focus
    lower_a_exercises = [
        ("Leg Press", 1, 3, 6, 10, 2, 180),
        ("Leg Extension", 2, 3, 8, 12, 2, 120),
        ("Leg Curl", 3, 3, 8, 12, 2, 120),
        ("Dumbbell Lunge", 4, 3, 8, 12, 2, 150),
    ]

    # Upper B - Pull focus
    upper_b_exercises = [
        ("Lat Pulldown", 1, 3, 6, 10, 2, 180),
        ("Dumbbell Bench Press", 2, 3, 6, 10, 2, 180),
        ("Dumbbell Row", 3, 3, 6, 10, 2, 150),
        ("Dumbbell Shoulder Press", 4, 3, 6, 10, 2, 150),
        ("Hammer Curl", 5, 3, 8, 12, 2, 90),
        ("Cable Overhead Tricep Extension", 6, 3, 8, 12, 2, 90),
    ]

    # Lower B - Hamstring focus
    lower_b_exercises = [
        ("Dumbbell RDL", 1, 3, 6, 10, 2, 180),
        ("Leg Press", 2, 3, 8, 12, 2, 150),
        ("Leg Curl", 3, 3, 8, 12, 2, 120),
        ("Leg Extension", 4, 3, 8, 12, 2, 120),
    ]

    # Add exercises to templates
    for name, order, sets, rmin, rmax, rir, rest in upper_a_exercises:
        repo.add_exercise_to_template(upper_a, exercise_ids[name], order, sets, rmin, rmax, rir, rest)

    for name, order, sets, rmin, rmax, rir, rest in lower_a_exercises:
        repo.add_exercise_to_template(lower_a, exercise_ids[name], order, sets, rmin, rmax, rir, rest)

    for name, order, sets, rmin, rmax, rir, rest in upper_b_exercises:
        repo.add_exercise_to_template(upper_b, exercise_ids[name], order, sets, rmin, rmax, rir, rest)

    for name, order, sets, rmin, rmax, rir, rest in lower_b_exercises:
        repo.add_exercise_to_template(lower_b, exercise_ids[name], order, sets, rmin, rmax, rir, rest)

    print("Workout program seeded successfully!")


if __name__ == "__main__":
    init_database()
    seed_workout_program()
    print("Database setup complete!")
