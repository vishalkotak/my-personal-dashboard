"""
WHOOP Health Data Client

A Python client to fetch health data from your WHOOP account using the official API.

Setup Instructions:
1. Go to https://developer.whoop.com and log in with your WHOOP account
2. Navigate to "Dashboard" and click "Create New Application"
3. Fill in the application details:
   - Name: Your app name (e.g., "My Health App")
   - Description: Brief description
   - Redirect URI: http://localhost:8080/callback
4. After creation, copy your Client ID and Client Secret
5. Create a .env file in this directory with:
   WHOOP_CLIENT_ID=your_client_id
   WHOOP_CLIENT_SECRET=your_client_secret
6. Run this script to authenticate and fetch your data
"""

import os
import json
import webbrowser
import http.server
import urllib.parse
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# WHOOP API Configuration
WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer"

# OAuth Configuration
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = [
    "offline",  # Required to get refresh tokens
    "read:profile",
    "read:body_measurement",
    "read:cycles",
    "read:recovery",
    "read:sleep",
    "read:workout",
]

TOKEN_FILE = ".whoop_token.json"


@dataclass
class WhoopTokens:
    """Stores OAuth tokens."""
    access_token: str
    expires_at: datetime
    refresh_token: Optional[str] = None

    def is_expired(self) -> bool:
        return datetime.now() >= self.expires_at

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WhoopTokens":
        return cls(
            access_token=data["access_token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            refresh_token=data.get("refresh_token"),
        )


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth callback."""

    authorization_code: Optional[str] = None

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            OAuthCallbackHandler.authorization_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body>
                <h1>Authentication Successful!</h1>
                <p>You can close this window and return to your terminal.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error = params.get("error", ["Unknown error"])[0]
            self.wfile.write(f"<html><body><h1>Error: {error}</h1></body></html>".encode())

    def log_message(self, format, *args):
        pass  # Suppress logging


class WhoopClient:
    """Client for interacting with the WHOOP API."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tokens: Optional[WhoopTokens] = None
        self._load_tokens()

    def _load_tokens(self):
        """Load tokens from file if available."""
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, "r") as f:
                    data = json.load(f)
                self.tokens = WhoopTokens.from_dict(data)
                print("Loaded existing tokens from file.")
            except Exception as e:
                print(f"Could not load tokens: {e}")

    def _save_tokens(self):
        """Save tokens to file."""
        if self.tokens:
            with open(TOKEN_FILE, "w") as f:
                json.dump(self.tokens.to_dict(), f, indent=2)
            print("Tokens saved to file.")

    def authenticate(self):
        """Perform OAuth authentication flow."""
        if self.tokens and not self.tokens.is_expired():
            print("Using existing valid tokens.")
            return

        if self.tokens and self.tokens.is_expired():
            print("Tokens expired, attempting refresh...")
            if self._refresh_token():
                return

        # Start OAuth flow
        print("Starting OAuth authentication...")
        self._oauth_flow()

    def _oauth_flow(self):
        """Execute the OAuth authorization code flow."""
        # Build authorization URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": "whoop_auth",
        }
        auth_url = f"{WHOOP_AUTH_URL}?{urllib.parse.urlencode(params)}"

        print(f"\nOpening browser for authentication...")
        print(f"If browser doesn't open, visit:\n{auth_url}\n")
        webbrowser.open(auth_url)

        # Start local server to capture callback
        server = http.server.HTTPServer(("localhost", 8080), OAuthCallbackHandler)
        print("Waiting for authentication callback...")

        while OAuthCallbackHandler.authorization_code is None:
            server.handle_request()

        server.server_close()
        code = OAuthCallbackHandler.authorization_code
        OAuthCallbackHandler.authorization_code = None

        # Exchange code for tokens
        self._exchange_code(code)

    def _exchange_code(self, code: str):
        """Exchange authorization code for tokens."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        response = requests.post(WHOOP_TOKEN_URL, data=data)
        response.raise_for_status()

        token_data = response.json()
        self.tokens = WhoopTokens(
            access_token=token_data["access_token"],
            expires_at=datetime.now() + timedelta(seconds=token_data["expires_in"] - 60),
            refresh_token=token_data.get("refresh_token"),
        )
        self._save_tokens()
        print("Authentication successful!")

    def _refresh_token(self) -> bool:
        """Refresh the access token."""
        if not self.tokens or not self.tokens.refresh_token:
            return False

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.tokens.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(WHOOP_TOKEN_URL, data=data)
            response.raise_for_status()

            token_data = response.json()
            self.tokens = WhoopTokens(
                access_token=token_data["access_token"],
                expires_at=datetime.now() + timedelta(seconds=token_data["expires_in"] - 60),
                refresh_token=token_data.get("refresh_token", self.tokens.refresh_token),
            )
            self._save_tokens()
            print("Token refreshed successfully!")
            return True
        except Exception as e:
            print(f"Token refresh failed: {e}")
            return False

    def _get_headers(self) -> dict:
        """Get authorization headers."""
        if not self.tokens:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        if self.tokens.is_expired():
            if not self._refresh_token():
                raise RuntimeError("Token expired and refresh failed.")

        return {
            "Authorization": f"Bearer {self.tokens.access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the API."""
        url = f"{WHOOP_API_BASE}{endpoint}"
        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        return response.json()

    def _get_paginated(self, endpoint: str, start: datetime, end: datetime) -> list:
        """Fetch all pages of a paginated endpoint."""
        results = []
        # Format as ISO 8601 with Z suffix (API expects UTC)
        start_str = start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_str = end.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        params = {
            "start": start_str,
            "end": end_str,
            "limit": 25,
        }

        while True:
            data = self._get(endpoint, params)
            results.extend(data.get("records", []))

            next_token = data.get("next_token")
            if not next_token:
                break
            params["nextToken"] = next_token

        return results

    # ========== API Methods ==========

    def get_profile(self) -> dict:
        """Get user profile information."""
        return self._get("/v2/user/profile/basic")

    def get_body_measurements(self) -> dict:
        """Get body measurements (height, weight, max heart rate)."""
        return self._get("/v2/user/measurement/body")

    def get_cycles(self, start: datetime, end: datetime) -> list:
        """
        Get physiological cycles (daily periods from wake to wake).

        Returns cycle data including:
        - Strain score
        - Kilojoules burned
        - Average heart rate
        """
        return self._get_paginated("/v2/cycle", start, end)

    def get_recovery(self, start: datetime, end: datetime) -> list:
        """
        Get recovery data for a date range.

        Returns recovery metrics including:
        - Recovery score (0-100%)
        - Resting heart rate
        - Heart rate variability (HRV)
        - SpO2 percentage
        - Skin temperature
        """
        return self._get_paginated("/v2/recovery", start, end)

    def get_sleep(self, start: datetime, end: datetime) -> list:
        """
        Get sleep data for a date range.

        Returns sleep metrics including:
        - Total sleep time
        - Sleep stages (REM, deep, light, awake)
        - Sleep efficiency
        - Respiratory rate
        - Sleep performance percentage
        """
        return self._get_paginated("/v2/activity/sleep", start, end)

    def get_workouts(self, start: datetime, end: datetime) -> list:
        """
        Get workout data for a date range.

        Returns workout data including:
        - Sport type
        - Strain score
        - Average/max heart rate
        - Calories burned
        - Distance (if applicable)
        """
        return self._get_paginated("/v2/activity/workout", start, end)

    def get_all_health_data(self, days: int = 7) -> dict:
        """
        Fetch all available health data for the specified number of days.

        Returns a dictionary with all health metrics.
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        print(f"Fetching health data from {start.date()} to {end.date()}...")

        data = {
            "profile": self.get_profile(),
            "body_measurements": self.get_body_measurements(),
            "cycles": self.get_cycles(start, end),
            "recovery": self.get_recovery(start, end),
            "sleep": self.get_sleep(start, end),
            "workouts": self.get_workouts(start, end),
            "date_range": {
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
        }

        print(f"Fetched: {len(data['cycles'])} cycles, {len(data['recovery'])} recovery records, "
              f"{len(data['sleep'])} sleep records, {len(data['workouts'])} workouts")

        return data


def main():
    """Main entry point."""
    client_id = os.getenv("WHOOP_CLIENT_ID")
    client_secret = os.getenv("WHOOP_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: Missing credentials!")
        print("\nPlease create a .env file with:")
        print("  WHOOP_CLIENT_ID=your_client_id")
        print("  WHOOP_CLIENT_SECRET=your_client_secret")
        print("\nGet these from https://developer.whoop.com")
        return

    # Create client and authenticate
    client = WhoopClient(client_id, client_secret)
    client.authenticate()

    # Fetch last 7 days of health data
    health_data = client.get_all_health_data(days=30)

    # Save to file
    output_file = "whoop_health_data.json"
    with open(output_file, "w") as f:
        json.dump(health_data, f, indent=2, default=str)
    print(f"\nHealth data saved to {output_file}")

    # Print summary
    print("\n" + "=" * 50)
    print("HEALTH DATA SUMMARY")
    print("=" * 50)

    profile = health_data["profile"]
    print(f"\nUser: {profile.get('first_name', 'N/A')} {profile.get('last_name', '')}")

    body = health_data["body_measurements"]
    print(f"Max Heart Rate: {body.get('max_heart_rate', 'N/A')} bpm")

    # Show recent recovery scores
    if health_data["recovery"]:
        print("\nRecent Recovery Scores:")
        for rec in health_data["recovery"][:5]:
            score = rec.get("score", {})
            date = rec.get("created_at", "")[:10]
            recovery_score = score.get("recovery_score", "N/A")
            hrv = score.get("hrv_rmssd_milli", "N/A")
            rhr = score.get("resting_heart_rate", "N/A")
            print(f"  {date}: Recovery {recovery_score}%, HRV {hrv}ms, RHR {rhr}bpm")

    # Show recent sleep
    if health_data["sleep"]:
        print("\nRecent Sleep:")
        for sleep in health_data["sleep"][:5]:
            score = sleep.get("score", {})
            stage = score.get("stage_summary", {})
            start = sleep.get("start", "")[:10]
            # Calculate total sleep (light + deep + REM)
            total_sleep_ms = (
                stage.get("total_light_sleep_time_milli", 0) +
                stage.get("total_slow_wave_sleep_time_milli", 0) +
                stage.get("total_rem_sleep_time_milli", 0)
            )
            total_hours = total_sleep_ms / 3600000
            efficiency = score.get("sleep_efficiency_percentage", "N/A")
            performance = score.get("sleep_performance_percentage", "N/A")
            print(f"  {start}: {total_hours:.1f}h sleep, {efficiency:.0f}% efficiency, {performance:.0f}% performance")


if __name__ == "__main__":
    main()
