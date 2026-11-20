"""Screenshot of the ProactiveHealth physician dashboard for Paper B (needs Playwright + Chrome)."""
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from proactivehealth.dashboard import create_app  # noqa: E402

app = create_app()
srv = make_server("127.0.0.1", 5057, app)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    pg = b.new_page(viewport={"width": 1240, "height": 760}, device_scale_factor=2)
    pg.goto("http://127.0.0.1:5057/?p=P0001")
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(ROOT / "docs" / "paper_b" / "dashboard.png"), full_page=True)
    b.close()
srv.shutdown()
print("ok")
