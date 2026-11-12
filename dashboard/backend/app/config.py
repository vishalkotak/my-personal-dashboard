"""Settings, read once from the environment (and the gitignored dashboard/.env)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"  # dashboard/.env


@dataclass(frozen=True)
class Settings:
    demo: bool
    database_url: str | None
    tz_name: str
    user_id: str | None
    frontend_origins: tuple[str, ...]
    port: int
    statement_timeout_ms: int
    types_path: Path | None = None  # None -> apple-health-sync/HealthSync/HealthTypes.json

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env: dict[str, str] | None = None) -> Settings:
    if env is None:
        # Real environment variables win over the .env file.
        load_dotenv(ENV_FILE, override=False)
        env = dict(os.environ)

    tz_name = env.get("TZ_NAME") or "America/Los_Angeles"
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise SystemExit(f"TZ_NAME={tz_name!r} is not a valid IANA time zone") from e

    frontend_port = int(env.get("FRONTEND_PORT") or 5173)
    database_url = (env.get("DATABASE_URL") or "").strip() or None
    demo = _truthy(env.get("DEMO"))

    user_id = (env.get("HEALTH_USER_ID") or "").strip() or None
    if user_id is not None:
        try:
            user_id = str(uuid.UUID(user_id))
        except ValueError as e:
            raise SystemExit("HEALTH_USER_ID must be a UUID (the ID shown in the iPhone app)") from e

    return Settings(
        demo=demo,
        database_url=database_url,
        tz_name=tz_name,
        user_id=user_id,
        frontend_origins=(
            f"http://localhost:{frontend_port}",
            f"http://127.0.0.1:{frontend_port}",
        ),
        port=int(env.get("API_PORT") or 8000),
        statement_timeout_ms=int(env.get("STATEMENT_TIMEOUT_MS") or 15000),
        types_path=Path(env["HEALTH_TYPES_PATH"]).expanduser() if env.get("HEALTH_TYPES_PATH") else None,
    )
