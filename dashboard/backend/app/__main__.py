"""Run the API: `python -m app`. Always binds to 127.0.0.1 (this machine only)."""

import logging

import uvicorn

from .config import load_settings

HOST = "127.0.0.1"  # deliberately not configurable: health data stays on this machine


def main() -> None:
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
