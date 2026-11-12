"""Regenerate the README screenshots from demo mode.

    DEMO=1 DEMO_NOW=2026-11-11T18:30:00-08:00 ./dashboard/start.sh
    pip install playwright && playwright install chromium   # once, anywhere
    python dashboard/scripts/screenshots.py                  # writes docs/screenshots/

The browser clock is pinned to the same moment as DEMO_NOW so "today" matches.
"""

import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

NOW = datetime.fromisoformat("2026-11-11T18:30:00-08:00")
URL = "http://localhost:5173"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "docs" / "screenshots")

SHOTS = [  # (file name, hash route, color scheme)
    ("overview-light", "overview", "light"),
    ("overview-dark", "overview", "dark"),
    ("activity-light", "activity?range=30d", "light"),
    ("heart-light", "heart?range=90d", "light"),
    ("sleep-dark", "sleep?range=30d", "dark"),
    ("body-light", "body?range=90d", "light"),
    ("workouts-dark", "workouts?range=90d", "dark"),
    ("explore-light", "explore?range=30d&type=HKQuantityTypeIdentifierDietaryProtein", "light"),
    ("explore-headache-light", "explore?range=1y&type=HKCategoryTypeIdentifierHeadache", "light"),
]

OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    for name, route, scheme in SHOTS:
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            color_scheme=scheme,
            device_scale_factor=1.5,
            timezone_id="America/Los_Angeles",
        )
        page = ctx.new_page()
        page.clock.set_fixed_time(NOW)
        page.goto(f"{URL}/#/{route}")
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / f"{name}.png", full_page=True)
        ctx.close()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, timezone_id="America/Los_Angeles")
    page = ctx.new_page()
    page.clock.set_fixed_time(NOW)
    page.goto(f"{URL}/#/overview")
    page.wait_for_timeout(1500)
    page.screenshot(path=OUT / "overview-phone.png", full_page=True)
    browser.close()
print(f"wrote {len(SHOTS) + 1} screenshots to {OUT}")
