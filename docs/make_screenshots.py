"""Capture UI screenshots of the demo for the README and paper.

Runs the demo in-process, drives the full flow (reading -> nurse approval -> share ->
school acceptance) in headless Chrome via Playwright, and saves PNGs to docs/screens/.

Usage:  python docs/make_screenshots.py [--chrome /usr/bin/google-chrome]
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from werkzeug.serving import make_server  # noqa: E402

from verifiedfever.app import create_app  # noqa: E402

OUT = ROOT / "docs" / "screens"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    app = create_app()
    srv = make_server("127.0.0.1", 5077, app)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:5077"
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=args.chrome, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1180, "height": 900}, device_scale_factor=2)
        pg.goto(base + "/")
        pg.screenshot(path=str(OUT / "overview.png"), full_page=True)
        # 1. parent takes a reading for Aarav (normal 36.3 C)
        pg.goto(base + "/parent?student_id=S-1001")
        pg.fill("input[name=temp_c]", "37.6")
        pg.click("button:has-text('Take signed reading')")
        pg.wait_for_load_state()
        pg.locator(".phone").first.screenshot(path=str(OUT / "parent_reading.png"))
        # 2. nurse approves
        pg.goto(base + "/nurse")
        pg.locator(".card").nth(1).screenshot(path=str(OUT / "nurse.png"))
        pg.set_viewport_size({"width": 640, "height": 900})
        pg.locator(".card").nth(1).screenshot(path=str(OUT / "nurse_narrow.png"))
        pg.set_viewport_size({"width": 1180, "height": 900})
        pg.click("button:has-text('Approve')")
        pg.wait_for_load_state()
        # 3. parent shares with school
        pg.goto(base + "/parent?student_id=S-1001")
        pg.click("button:has-text('Share with school')")
        pg.wait_for_load_state()
        pg.click("button:has-text('Send to school')")
        pg.wait_for_load_state()
        pg.locator(".phone").first.screenshot(path=str(OUT / "parent_share.png"))
        # 4. school portal
        pg.goto(base + "/school")
        pg.locator(".row").first.screenshot(path=str(OUT / "school.png"))
        pg.set_viewport_size({"width": 640, "height": 900})
        cards = pg.locator(".row").first.locator(".card")
        cards.nth(0).screenshot(path=str(OUT / "school_receive_narrow.png"))
        cards.nth(1).screenshot(path=str(OUT / "school_accepted_narrow.png"))
        b.close()
    srv.shutdown()
    print("screens written to", OUT)


if __name__ == "__main__":
    main()
