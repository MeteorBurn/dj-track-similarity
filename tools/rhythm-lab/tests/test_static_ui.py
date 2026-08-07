from __future__ import annotations

import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

import pytest
import uvicorn


LAB_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = LAB_ROOT.parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from rhythm_lab.lab_db import RhythmLabDatabase  # noqa: E402
from rhythm_lab.web_app import create_app  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_node_playwright(script: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for Rhythm Lab static UI regression tests")
    playwright_module = PROJECT_ROOT / "frontend" / "node_modules" / "playwright"
    if not playwright_module.exists():
        pytest.skip("frontend Playwright dependency is not installed")
    return subprocess.run(
        ["node", "-e", script],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_clearing_profile_cancels_in_flight_track_load(tmp_path: Path) -> None:
    """Catches stale async loads reading the cleared active profile."""

    labels_path = tmp_path / "rhythm_lab.sqlite"
    RhythmLabDatabase(labels_path).create_profile(
        classifier_key="focused",
        name="Focused",
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
            {"key": "review", "name": "Review", "role": "review"},
        ],
    )
    port = _free_port()
    app = create_app(labels_db_path=labels_path)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urlopen(
                    f"http://127.0.0.1:{port}/api/source/current",
                    timeout=1,
                ) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        else:
            pytest.fail("Rhythm Lab test server did not start")

        script = f"""
const {{ chromium }} = require("./frontend/node_modules/playwright");
(async () => {{
  const browser = await chromium.launch({{ headless: true }});
  const page = await browser.newPage();
  const events = [];
  page.on("console", msg => events.push({{ type: msg.type(), text: msg.text() }}));
  page.on("pageerror", err => events.push({{ type: "pageerror", text: err.stack || err.message }}));
  await page.route("**/api/profiles/focused/tracks?**", async route => {{
    await new Promise(resolve => setTimeout(resolve, 350));
    await route.continue();
  }});
  await page.goto("http://127.0.0.1:{port}/", {{ waitUntil: "networkidle" }});
  await page.locator("#profileSelect").selectOption("focused");
  await page.locator("#profileSelect").selectOption("");
  await page.waitForTimeout(1000);
  const statusText = await page.locator("#refreshCandidatesStatus").textContent();
  await browser.close();
  console.log(JSON.stringify({{ events, statusText }}));
  if (events.length || /Cannot read properties/.test(statusText || "")) {{
    process.exit(2);
  }}
}})().catch(error => {{
  console.error(error.stack || error.message);
  process.exit(1);
}});
"""
        completed = _run_node_playwright(script)
        if completed.returncode != 0:
            details = completed.stdout.strip()
            try:
                details = json.dumps(json.loads(details), indent=2)
            except json.JSONDecodeError:
                details = "\n".join(
                    part
                    for part in (completed.stdout.strip(), completed.stderr.strip())
                    if part
                )
            pytest.fail(f"Rhythm Lab stale profile load surfaced a UI error:\n{details}")
    finally:
        server.should_exit = True
        thread.join(timeout=5)
