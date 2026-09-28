"""Capture C-Sync screenshots for the final report.

Drives the locally installed Chrome in headless mode over the DevTools
protocol. No extra packages: tornado (a Streamlit dependency) supplies the
websocket client. Start C-Sync first (python -m streamlit run c_sync/app.py
--server.port 8502), then:

    python 03_assets/report/capture_screenshots.py [--app http://localhost:8502/]

Only navigation, expanders and "Reveal the scores" are clicked. "Draft the fix",
the Ask buttons and the review buttons are never pressed, so the capture makes
no model calls and writes no review decisions.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from tornado.websocket import websocket_connect

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "03_assets" / "screenshots"
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
]
DEBUG_PORT = 9333
WIDTH, HEIGHT, SCALE = 1280, 800, 2
HOME_WIDTH = 1600


class CDP:
    """Just enough of the DevTools protocol: send a command, await its reply."""

    def __init__(self, ws):
        self.ws, self.n, self.pending = ws, 0, {}
        self.reader = asyncio.ensure_future(self._read())

    @classmethod
    async def connect(cls, url: str) -> "CDP":
        return cls(await websocket_connect(url, max_message_size=1 << 30))

    async def _read(self) -> None:
        while True:
            msg = await self.ws.read_message()
            if msg is None:
                return
            data = json.loads(msg)
            fut = self.pending.pop(data.get("id"), None)
            if fut and not fut.done():
                fut.set_result(data)

    async def send(self, method: str, **params) -> dict:
        self.n += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.n] = fut
        await self.ws.write_message(json.dumps({"id": self.n, "method": method, "params": params}))
        data = await asyncio.wait_for(fut, 90)
        if "error" in data:
            raise RuntimeError(f"{method}: {data['error']}")
        return data.get("result", {})

    async def js(self, expression: str):
        result = await self.send("Runtime.evaluate", expression=expression,
                                 returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"].get("text", "script error"))
        return result["result"].get("value")


# --- page helpers -----------------------------------------------------------

async def settle(cdp: CDP, marker: str, timeout: float = 45) -> None:
    """Wait for `marker` text, no stale (re-running) elements, and a DOM that
    has stopped changing; then let the entrance animations finish."""
    deadline = time.monotonic() + timeout
    stable, last = 0, None
    while time.monotonic() < deadline:
        state = await cdp.js(
            "(() => ({has: document.body.innerText.includes(%s),"
            " stale: document.querySelectorAll('[data-stale=\"true\"]').length,"
            " size: document.body.innerHTML.length}))()" % json.dumps(marker))
        if state["has"] and not state["stale"]:
            stable = stable + 1 if state["size"] == last else 0
            last = state["size"]
            if stable >= 3:
                await asyncio.sleep(2.2)
                return
        await asyncio.sleep(0.4)
    raise TimeoutError(f"page never settled on {marker!r}")


async def click_button(cdp: CDP, label: str, scope: str = "document") -> None:
    ok = await cdp.js(
        "(() => { const root = %s; const want = %s;"
        " const b = [...root.querySelectorAll('button')].find(x => {"
        "   const md = x.querySelector('[data-testid=\"stMarkdownContainer\"]');"
        "   const t = (md ? md.innerText : x.innerText || '').trim();"
        "   return t === want || t.endsWith(want); });"
        " if (!b) return false; b.click(); return true; })()" % (scope, json.dumps(label)))
    if not ok:
        raise LookupError(f"no button labelled {label!r}")


async def nav(cdp: CDP, page: str, marker: str) -> None:
    await click_button(cdp, page, "document.querySelector('[data-testid=\"stSidebar\"]')")
    await settle(cdp, marker)


async def open_expander(cdp: CDP, label: str) -> None:
    ok = await cdp.js(
        "(() => { const s = [...document.querySelectorAll('[data-testid=\"stExpander\"] summary')]"
        ".find(x => x.innerText.includes(%s)); if (!s) return false;"
        " if (!s.parentElement.open) s.click(); return true; })()" % json.dumps(label))
    if not ok:
        raise LookupError(f"no expander {label!r}")
    await asyncio.sleep(1.0)


async def open_evidence(cdp: CDP, text: str) -> None:
    await cdp.js(
        "(() => { const d = [...document.querySelectorAll('.cs-ev details')]"
        ".find(x => x.innerText.includes(%s)); if (d) d.open = true; })()" % json.dumps(text))
    await asyncio.sleep(0.6)


async def content_height(cdp: CDP) -> int:
    return int(await cdp.js(
        "(() => { let h = document.documentElement.scrollHeight;"
        " for (const s of ['[data-testid=\"stMain\"]','[data-testid=\"stAppViewContainer\"]','section.main'])"
        " { const el = document.querySelector(s); if (el) h = Math.max(h, el.scrollHeight); }"
        " return h; })()"))


async def viewport(cdp: CDP, width: int, height: int) -> None:
    await cdp.send("Emulation.setDeviceMetricsOverride", width=width, height=height,
                   deviceScaleFactor=SCALE, mobile=False)


async def shoot(cdp: CDP, name: str, full: bool = True, width: int = WIDTH) -> Path:
    """Screenshot the page. full=True grows the viewport to the content height
    first, because Streamlit scrolls inside a container, not the document."""
    if full:
        height = HEIGHT
        for _ in range(4):
            wanted = max(HEIGHT, await content_height(cdp))
            if wanted == height:
                break
            height = wanted
            await viewport(cdp, width, height)
            await asyncio.sleep(0.9)
    shot = await cdp.send("Page.captureScreenshot", format="png", fromSurface=True)
    path = OUT / f"{name}.png"
    path.write_bytes(base64.b64decode(shot["data"]))
    await viewport(cdp, width, HEIGHT)
    await asyncio.sleep(0.5)
    print(f"  saved {path.relative_to(REPO)}")
    return path


# --- the tour -----------------------------------------------------------------

async def tour(app: str) -> None:
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/list").read())
    page = next(t for t in targets if t.get("type") == "page")
    cdp = await CDP.connect(page["webSocketDebuggerUrl"])
    await cdp.send("Page.enable")
    await cdp.send("Runtime.enable")
    # Home is shot wider: at 1280px the five funnel squares wrap onto two rows
    await viewport(cdp, HOME_WIDTH, HEIGHT)
    await cdp.send("Page.navigate", url=app)
    await settle(cdp, "From noise to curriculum.")
    await shoot(cdp, "01_home", width=HOME_WIDTH)
    await viewport(cdp, WIDTH, HEIGHT)

    await nav(cdp, "Dashboard", "Every recommendation in the run")
    await shoot(cdp, "02_dashboard")

    await nav(cdp, "Radar", "Technology radar")
    await shoot(cdp, "03_radar", full=False)

    await nav(cdp, "Trend story", "Why is this trending?")
    await open_evidence(cdp, "Release check")
    await shoot(cdp, "04_trend_story")

    await nav(cdp, "The gap", "Is this trend already taught?")
    await open_expander(cdp, "Read the cited course content")
    await shoot(cdp, "05_gap")

    await nav(cdp, "Evaluation", "How important is this?")
    await click_button(cdp, "Reveal the scores", "document.querySelector('[data-testid=\"stMain\"]')")
    await settle(cdp, "OVERALL")
    await shoot(cdp, "06_evaluation")

    await nav(cdp, "Decision", "What should we do?")
    await open_expander(cdp, "Evidence chain")
    await shoot(cdp, "07_decision")

    await nav(cdp, "Ask", "Ask about a recommendation")
    await shoot(cdp, "08_ask")

    await nav(cdp, "How it works", "How does C-sync work?")
    await shoot(cdp, "09_how_it_works")
    cdp.reader.cancel()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app", default="http://localhost:8502/")
    args = parser.parse_args()
    chrome = next((c for c in CHROME_CANDIDATES if Path(c).is_file()), None)
    if not chrome:
        sys.exit("Chrome or Edge not found")
    OUT.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="csync-shots-")
    proc = subprocess.Popen([chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
                             f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                             "--disable-extensions", "--hide-scrollbars", "--force-color-profile=srgb",
                             f"--window-size={WIDTH},{HEIGHT}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(tour(args.app))
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
