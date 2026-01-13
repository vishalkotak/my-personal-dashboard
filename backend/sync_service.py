"""
WHOOP Data Sync Service

Handles syncing data from WHOOP API to local database.
Includes backfill logic for missing data and email alerting.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, date, timezone
from typing import List, Optional
from dotenv import load_dotenv

from database import init_database, HealthDataRepository
from whoop_client import WhoopClient

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Email configuration
ALERT_EMAIL = "vishalkt07@gmail.com"
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # App password for Gmail


class SyncService:
    """Service for syncing WHOOP data to local database."""

    def __init__(self):
        self.repo = HealthDataRepository()
        self.client = None
        self.user_id = None

    def _get_client(self) -> WhoopClient:
        """Get authenticated WHOOP client."""
        if self.client is None:
            client_id = os.getenv("WHOOP_CLIENT_ID")
            client_secret = os.getenv("WHOOP_CLIENT_SECRET")

            if not client_id or not client_secret:
                raise ValueError("WHOOP credentials not configured")

            self.client = WhoopClient(client_id, client_secret)

            if not self.client.tokens:
                raise ValueError("Not authenticated with WHOOP. Run the API first to authenticate.")

        return self.client

    def _ensure_user(self) -> int:
        """Ensure user exists in database and return user ID."""
        if self.user_id is None:
            client = self._get_client()
            profile = client.get_profile()

            self.user_id = self.repo.get_or_create_user(
                whoop_user_id=profile['user_id'],
                email=profile.get('email'),
                first_name=profile.get('first_name'),
                last_name=profile.get('last_name')
            )

            # Also sync body measurements
            body = client.get_body_measurements()
            self.repo.upsert_body_measurements(
                user_id=self.user_id,
                height=body.get('height_meter'),
                weight=body.get('weight_kilogram'),
                max_hr=body.get('max_heart_rate'),
                recorded_date=date.today()
            )

        return self.user_id

    def sync_date_range(self, start_date: date, end_date: date) -> dict:
        """Sync all data for a date range."""
        logger.info(f"Syncing data from {start_date} to {end_date}")

        client = self._get_client()
        user_id = self._ensure_user()

        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        stats = {
            'cycles': 0,
            'recovery': 0,
            'sleep': 0,
            'workouts': 0,
            'errors': []
        }

        try:
            # Sync cycles
            cycles = client.get_cycles(start_dt, end_dt)
            for cycle in cycles:
                self.repo.upsert_cycle(user_id, cycle)
                stats['cycles'] += 1
            logger.info(f"Synced {stats['cycles']} cycles")

        except Exception as e:
            logger.error(f"Error syncing cycles: {e}")
            stats['errors'].append(f"Cycles: {str(e)}")

        try:
            # Sync recovery
            recovery_data = client.get_recovery(start_dt, end_dt)
            for recovery in recovery_data:
                self.repo.upsert_recovery(user_id, recovery)
                stats['recovery'] += 1
            logger.info(f"Synced {stats['recovery']} recovery records")

        except Exception as e:
            logger.error(f"Error syncing recovery: {e}")
            stats['errors'].append(f"Recovery: {str(e)}")

        try:
            # Sync sleep
            sleep_data = client.get_sleep(start_dt, end_dt)
            for sleep in sleep_data:
                self.repo.upsert_sleep(user_id, sleep)
                stats['sleep'] += 1
            logger.info(f"Synced {stats['sleep']} sleep records")

        except Exception as e:
            logger.error(f"Error syncing sleep: {e}")
            stats['errors'].append(f"Sleep: {str(e)}")

        try:
            # Sync workouts
            workouts = client.get_workouts(start_dt, end_dt)
            for workout in workouts:
                self.repo.upsert_workout(user_id, workout)
                stats['workouts'] += 1
            logger.info(f"Synced {stats['workouts']} workouts")

        except Exception as e:
            logger.error(f"Error syncing workouts: {e}")
            stats['errors'].append(f"Workouts: {str(e)}")

        return stats

    def sync_single_day(self, sync_date: date) -> dict:
        """Sync data for a single day."""
        return self.sync_date_range(sync_date, sync_date)

    def sync_yesterday(self) -> dict:
        """Sync yesterday's data (for daily cron job)."""
        yesterday = date.today() - timedelta(days=1)
        return self.sync_single_day(yesterday)

    def backfill_missing_days(self, max_days_back: int = 30) -> dict:
        """Find and sync any missing days."""
        logger.info(f"Checking for missing data in last {max_days_back} days")

        missing_dates = self.repo.get_missing_sync_dates(max_days_back)

        if not missing_dates:
            logger.info("No missing dates found")
            return {'missing_dates': [], 'synced': 0}

        logger.info(f"Found {len(missing_dates)} missing dates: {missing_dates}")

        total_stats = {
            'missing_dates': [d.isoformat() for d in missing_dates],
            'synced': 0,
            'errors': []
        }

        for missing_date in missing_dates:
            try:
                logger.info(f"Backfilling {missing_date}")
                stats = self.sync_single_day(missing_date)
                total_stats['synced'] += 1

                if stats['errors']:
                    total_stats['errors'].extend(stats['errors'])

            except Exception as e:
                logger.error(f"Failed to backfill {missing_date}: {e}")
                total_stats['errors'].append(f"{missing_date}: {str(e)}")

        return total_stats

    def full_sync(self, days: int = 30) -> dict:
        """Perform a full sync of the last N days."""
        logger.info(f"Starting full sync of last {days} days")

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        started_at = datetime.now()

        try:
            stats = self.sync_date_range(start_date, end_date)
            stats['success'] = len(stats['errors']) == 0

            # Log sync
            self.repo.log_sync(
                sync_date=date.today(),
                sync_type='full',
                status='success' if stats['success'] else 'partial',
                records_synced=stats['recovery'],
                error_message='; '.join(stats['errors']) if stats['errors'] else None,
                started_at=started_at,
                completed_at=datetime.now()
            )

            return stats

        except Exception as e:
            logger.error(f"Full sync failed: {e}")

            self.repo.log_sync(
                sync_date=date.today(),
                sync_type='full',
                status='failed',
                error_message=str(e),
                started_at=started_at,
                completed_at=datetime.now()
            )

            raise


class EmailAlerter:
    """Handles sending email alerts for sync failures."""

    @staticmethod
    def send_alert(subject: str, body: str, to_email: str = ALERT_EMAIL):
        """Send an email alert."""
        if not SMTP_USER or not SMTP_PASSWORD:
            logger.warning("Email credentials not configured. Skipping email alert.")
            logger.warning(f"Would have sent: {subject}")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = SMTP_USER
            msg['To'] = to_email
            msg['Subject'] = f"[WHOOP Sync Alert] {subject}"

            body_with_footer = f"""{body}

---
This is an automated alert from your WHOOP Health Dashboard.
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            msg.attach(MIMEText(body_with_footer, 'plain'))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)

            logger.info(f"Alert email sent to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False

    @staticmethod
    def send_sync_failure_alert(error_message: str, sync_date: date = None):
        """Send alert for sync failure."""
        subject = f"Sync Failed - {sync_date or date.today()}"
        body = f"""WHOOP data sync failed!

Date: {sync_date or date.today()}
Error: {error_message}

Please check the sync logs and retry manually if needed.

To retry, run:
  python sync_service.py --backfill
"""
        return EmailAlerter.send_alert(subject, body)

    @staticmethod
    def send_missing_data_alert(missing_dates: List[date]):
        """Send alert for missing data that couldn't be recovered."""
        subject = f"Missing Data Alert - {len(missing_dates)} days"
        body = f"""WHOOP data is missing for the following dates:

{chr(10).join(['  - ' + d.isoformat() for d in missing_dates])}

This may be due to:
- Laptop being offline/asleep
- WHOOP API issues
- Authentication expiry

The system will automatically retry, but you may want to check manually.
"""
        return EmailAlerter.send_alert(subject, body)


def run_daily_sync():
    """Run the daily sync job with error handling and alerting."""
    logger.info("=" * 50)
    logger.info("Starting daily sync job")
    logger.info("=" * 50)

    sync = SyncService()
    alerter = EmailAlerter()

    try:
        # First, try to backfill any missing days (handles laptop being off)
        backfill_result = sync.backfill_missing_days(max_days_back=7)

        if backfill_result['missing_dates']:
            logger.info(f"Backfilled {backfill_result['synced']} missing days")

            if backfill_result['errors']:
                # Some backfills failed
                failed_dates = [d for d in backfill_result['missing_dates']
                               if any(d in err for err in backfill_result['errors'])]
                if failed_dates:
                    alerter.send_missing_data_alert(
                        [date.fromisoformat(d) for d in failed_dates]
                    )

        # Sync yesterday's data
        yesterday = date.today() - timedelta(days=1)
        stats = sync.sync_single_day(yesterday)

        if stats['errors']:
            alerter.send_sync_failure_alert(
                '; '.join(stats['errors']),
                yesterday
            )

        # Log success
        sync.repo.log_sync(
            sync_date=yesterday,
            sync_type='daily',
            status='success' if not stats['errors'] else 'partial',
            records_synced=stats['recovery'],
            error_message='; '.join(stats['errors']) if stats['errors'] else None,
            started_at=datetime.now(),
            completed_at=datetime.now()
        )

        logger.info("Daily sync completed successfully")
        return True

    except Exception as e:
        logger.error(f"Daily sync failed: {e}")
        alerter.send_sync_failure_alert(str(e))

        sync.repo.log_sync(
            sync_date=date.today() - timedelta(days=1),
            sync_type='daily',
            status='failed',
            error_message=str(e),
            started_at=datetime.now(),
            completed_at=datetime.now()
        )

        return False


def main():
    """Main entry point with CLI arguments."""
    import argparse

    parser = argparse.ArgumentParser(description='WHOOP Data Sync Service')
    parser.add_argument('--init', action='store_true', help='Initialize database')
    parser.add_argument('--full-sync', type=int, metavar='DAYS', help='Full sync of last N days')
    parser.add_argument('--daily', action='store_true', help='Run daily sync (for cron)')
    parser.add_argument('--backfill', action='store_true', help='Backfill missing days')
    parser.add_argument('--stats', action='store_true', help='Show sync statistics')
    parser.add_argument('--test-email', action='store_true', help='Test email alerting')

    args = parser.parse_args()

    if args.init:
        init_database()
        print("Database initialized!")

    elif args.full_sync:
        init_database()
        sync = SyncService()
        stats = sync.full_sync(days=args.full_sync)
        print(f"\nSync complete!")
        print(f"  Cycles: {stats['cycles']}")
        print(f"  Recovery: {stats['recovery']}")
        print(f"  Sleep: {stats['sleep']}")
        print(f"  Workouts: {stats['workouts']}")
        if stats['errors']:
            print(f"  Errors: {stats['errors']}")

    elif args.daily:
        init_database()
        success = run_daily_sync()
        exit(0 if success else 1)

    elif args.backfill:
        init_database()
        sync = SyncService()
        result = sync.backfill_missing_days()
        print(f"Backfill complete. Synced {result['synced']} missing days.")
        if result['errors']:
            print(f"Errors: {result['errors']}")

    elif args.stats:
        repo = HealthDataRepository()
        stats = repo.get_sync_stats()
        print("\nSync Statistics:")
        print(f"  Total Recovery Records: {stats['total_recovery_records']}")
        print(f"  Total Sleep Records: {stats['total_sleep_records']}")
        print(f"  Total Workout Records: {stats['total_workout_records']}")
        print(f"  Date Range: {stats['date_range']['start']} to {stats['date_range']['end']}")
        print(f"  Recent Failures (7 days): {stats['recent_failures']}")

    elif args.test_email:
        print("Testing email alert...")
        success = EmailAlerter.send_alert(
            "Test Alert",
            "This is a test alert from your WHOOP sync service."
        )
        print("Email sent!" if success else "Email failed - check credentials")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
