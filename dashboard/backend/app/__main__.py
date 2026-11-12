"""Run the API: `python -m app`. Always binds to 127.0.0.1 (this machine only)."""

import logging
import os
import threading
import time

import uvicorn

from .config import load_settings

HOST = "127.0.0.1"  # deliberately not configurable: health data stays on this machine


def _exit_with_parent(parent_pid: int) -> None:
    """Used by the Mac app: if the app dies without stopping us (crash, force quit), exit too."""
    def watch() -> None:
        while os.getppid() == parent_pid:
            time.sleep(1)
        os._exit(0)

    threading.Thread(target=watch, daemon=True, name="parent-watch").start()


def main() -> None:
    if os.environ.get("HEALTHSYNC_PARENT_PID", "").isdigit():
        _exit_with_parent(int(os.environ["HEALTHSYNC_PARENT_PID"]))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    uvicorn.run(
        "app.api:create_app",
        factory=True,
        host=HOST,
        port=settings.port,
        log_level="info",
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
