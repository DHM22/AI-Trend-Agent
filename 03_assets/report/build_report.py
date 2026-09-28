"""Build the final report PDF from report.html.

    python 03_assets/report/build_report.py

Steps:
  1. figures/   crops and compresses the C-Sync screenshots in 03_assets/screenshots/
                (re-capture them with capture_screenshots.py) and copies the diagram.
  2. charts     drawn as inline SVG from the committed data, never typed in by hand:
                01_data/demo_snapshot.json, the signals file it names, and
                04_eval/results/*.json.
  3. render     headless Chrome prints the page twice: pass 1 finds the page each
                contents entry lands on (from the PDF's own links), pass 2 prints
                with those page numbers filled in.
  4. finish     PyMuPDF adds bookmarks and document metadata.

Needs Chrome or Edge, Pillow, PyMuPDF and tornado (installed with Streamlit).
The Inter and JetBrains Mono fonts load from Google Fonts, so build online.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pymupdf as fitz
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from capture_screenshots import CDP, CHROME_CANDIDATES  # noqa: E402

SHOTS = REPO / "03_assets" / "screenshots"
FIGURES = HERE / "figures"
SOURCE = HERE / "report.html"
RENDERED = HERE / "_render.html"
OUTPUT = HERE / "AI_Trend_Agent_Final_Report.pdf"
DEBUG_PORT = 9334

TEAM = ["Abdurahman Al-Duraywish", "Rafif Alsuhaibani", "Aldanah Aldosari", "Ruyuf Almajnooni"]
METADATA = {
    "title": "AI Trend Agent: Final Project Report",
    "author": ", ".join(TEAM),
    "subject": "Capstone project, SDA x WeCloudData Agentic AI Engineering Program",
    "keywords": "agentic AI, curriculum, RAG, verification, human in the loop, C-Sync",
    "creator": "03_assets/report/build_report.py (headless Chrome)",
}

# (screenshot, figure, crop box in screenshot pixels or None, output width)
FIGURE_SPECS = [
    ("01_home.png", "fig-home.jpg", None, 2200),
    ("02_dashboard.png", "fig-dashboard.jpg", (0, 0, 2560, 2905), 2000),           # first three rows of cards
    ("03_radar.png", "fig-radar.jpg", None, 2000),
    ("04_trend_story.png", "fig-trend-story.jpg", (0, 0, 2560, 2950), 2000),       # down to the evidence cards
    ("05_gap.png", "fig-gap.jpg", (0, 0, 2560, 3050), 2000),
    ("06_evaluation.png", "fig-evaluation.jpg", (0, 0, 2560, 1790), 2000),         # rings + matched material
    ("07_decision.png", "fig-decision-plan.jpg", (0, 0, 2560, 2920), 2000),        # recommendation, plan, fix button
    ("07_decision.png", "fig-decision-review.jpg", (600, 2930, 2560, 4640), 1960), # review panel + evidence chain
    ("08_ask.png", "fig-ask.jpg", None, 2000),
    ("09_how_it_works.png", "fig-how.jpg", None, 1600),
]


# --- 1. figures ---------------------------------------------------------------

def prepare_figures() -> None:
    FIGURES.mkdir(exist_ok=True)
    for src, dst, box, width in FIGURE_SPECS:
        im = Image.open(SHOTS / src).convert("RGB")
        if box:
            im = im.crop(box)
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(FIGURES / dst, "JPEG", quality=90, subsampling=0, optimize=True, progressive=True)
    shutil.copyfile(REPO / "03_assets" / "diagrams" / "architecture.png", FIGURES / "fig-architecture.png")
    print(f"  figures: {len(FIGURE_SPECS) + 1} written to {FIGURES.relative_to(REPO)}")


# --- 2. charts ------------------------------------------------------------------
# Thin marks, a 2px surface gap between stacked segments, 4px rounded data ends,
# hairline grid, text in ink tokens (never the series colour). The palette
# (#7c3aed, #0891b2) passed the dataviz validator on white: CVD dE 15.0, normal 24.5.

INK, INK2, MUTED, GRID = "#141827", "#434b61", "#6f7890", "#e6e8ef"
VIOLET, CYAN, GRAY = "#7c3aed", "#0891b2", "#c7ccd8"
FONT = "Inter, 'Segoe UI', system-ui, sans-serif"


def _t(x, y, text, size=11, weight=400, fill=INK, anchor="start", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}"{extra}>{html.escape(str(text))}</text>')


def _bar(x, y, w, h, fill, round_end=True, r=4.0):
    """A horizontal bar, square at the baseline, rounded at the data end."""
    if w <= 0:
        return ""
    r = min(r, w, h / 2) if round_end else 0
    if not r:
        return f'<path d="M{x:.2f},{y:.2f}h{w:.2f}v{h:.2f}h{-w:.2f}Z" fill="{fill}"/>'
    return (f'<path d="M{x:.2f},{y:.2f}h{w - r:.2f}a{r},{r} 0 0 1 {r},{r}v{h - 2 * r:.2f}'
            f'a{r},{r} 0 0 1 {-r},{r}h{-(w - r):.2f}Z" fill="{fill}"/>')


def _legend(x, y, items):
    out, cx = [], x
    for label, color in items:
        out.append(f'<rect x="{cx:.1f}" y="{y - 8.5:.1f}" width="10" height="10" rx="2.5" fill="{color}"/>')
        out.append(_t(cx + 15, y, label, 10.5, 500, INK2))
        cx += 15 + 6.1 * len(label) + 20
    return "".join(out)


def chart_tiers(snapshot: dict) -> str:
    rows = [("add_new_lesson", "Create a new lesson"), ("update_existing_material", "Update existing material"),
            ("add_optional_content", "Add optional content"), ("watch", "Keep watching")]
    series = [("lab", "Lab cell", VIOLET, "#ffffff"), ("slides", "Slide", CYAN, "#ffffff"),
              (None, "No curriculum match", GRAY, INK)]
    counts = {tier: {key: 0 for key, *_ in series} for tier, _ in rows}
    for rec in snapshot.get("recommendations") or []:
        kind = (rec.get("match") or {}).get("content_type")
        counts[rec["recommended_action"]][kind if kind in ("lab", "slides") else None] += 1
    top_total = max(sum(c.values()) for c in counts.values())
    xmax = max(4, math.ceil(top_total / 4) * 4)
    W, left, right, top, row_h, bar_h = 640, 170, 604, 44, 34, 18
    scale = (right - left) / xmax
    H = top + row_h * len(rows) + 30
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="{FONT}" role="img" '
           f'aria-label="Recommendations by action tier and cited material">']
    out.append(_legend(left, 16, [(label, color) for _, label, color, _ in series]))
    grid_bottom = top + row_h * len(rows) - 8
    for tick in range(0, xmax + 1, 4):
        x = left + tick * scale
        out.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{grid_bottom}" stroke="{GRID}" stroke-width="1"/>')
        out.append(_t(x, grid_bottom + 15, tick, 9.5, 500, MUTED, "middle", ' font-variant-numeric="tabular-nums"'))
    for i, (tier, label) in enumerate(rows):
        y = top + i * row_h
        cy = y + bar_h / 2 + 4
        out.append(_t(left - 12, cy, label, 11, 600, INK, "end"))
        segs = [(counts[tier][key], color, text_fill) for key, _, color, text_fill in series if counts[tier][key]]
        x, total = left, sum(n for n, *_ in segs)
        for j, (n, color, text_fill) in enumerate(segs):
            w = n * scale - (2 if j < len(segs) - 1 else 0)          # 2px surface gap
            out.append(_bar(x, y, w, bar_h, color, round_end=(j == len(segs) - 1)))
            if w >= 18:
                out.append(_t(x + w / 2, cy - 0.5, n, 9.5, 700, text_fill, "middle"))
            x += n * scale
        out.append(_t(left + total * scale + 7, cy, total, 11, 700, INK))
    out.append("</svg>")
    return "".join(out)


RELEASE_ROWS = [("openai/openai-python", "openai-python"), ("langchain-ai/langsmith-sdk", "langsmith-sdk"),
                ("langchain-ai/langchain", "langchain"), ("langchain-ai/langgraph", "langgraph")]


def chart_releases(signals: list[dict]) -> str:
    """One dot per stable release over the four weeks before the capture."""
    days = {repo: [] for repo, _ in RELEASE_ROWS}
    for s in signals:
        repo = s["title"].split(":", 1)[0]
        if s.get("source") == "github" and repo in days and s.get("published"):
            days[repo].append(date.fromisoformat(s["published"][:10]))
    end = max(d for ds in days.values() for d in ds)
    start = end - timedelta(days=28)
    W, left, right, top, row_h = 640, 118, 588, 26, 38
    span = (end - start).days
    x = lambda d: left + (d - start).days / span * (right - left)  # noqa: E731
    grid_bottom = top + row_h * len(RELEASE_ROWS)
    H = grid_bottom + 24
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="{FONT}" role="img" '
           f'aria-label="Stable releases per repository in the four weeks before the capture">']
    out.append(_t(W - 2, 12, "Releases", 9.5, 700, MUTED, "end"))
    for k in range(0, span + 1, 7):
        d = start + timedelta(days=k)
        out.append(f'<line x1="{x(d):.1f}" y1="{top - 6}" x2="{x(d):.1f}" y2="{grid_bottom}" stroke="{GRID}" stroke-width="1"/>')
        out.append(_t(x(d), grid_bottom + 15, f"{d.day} {d:%b}", 9.5, 500, MUTED, "middle"))
    for i, (repo, label) in enumerate(RELEASE_ROWS):
        cy = top + i * row_h + row_h / 2
        out.append(f'<line x1="{left}" y1="{cy:.1f}" x2="{right}" y2="{cy:.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(_t(left - 12, cy + 4, label, 11, 600, INK, "end"))
        for d, n in sorted(Counter(days[repo]).items()):
            for k in range(n):                      # same-day releases stack, ringed in the surface colour
                cyk = cy + (k - (n - 1) / 2) * 8.6
                out.append(f'<circle cx="{x(d):.1f}" cy="{cyk:.1f}" r="4.2" fill="{VIOLET}" stroke="#ffffff" stroke-width="1.5"/>')
        out.append(_t(W - 2, cy + 4, len(days[repo]), 11, 700, INK, "end"))
    out.append("</svg>")
    return "".join(out)


EVAL_RUNS = [
    ("rescored_1_pre_restore_nokey.json", "Pre-restore verifier", "source-tier fallback, offline"),
    ("rescored_2_restored_before_fixes_nokey.json", "Restored verifier", "before fixes, offline"),
    ("rescored_3_restored_fixed_nokey.json", "Restored + 4 fixes", "offline, no model"),
    ("live_baseline_fixed_harness.json", "Restored + 4 fixes", "live gpt-4o-mini, 3 repeats"),
]


def chart_eval() -> str:
    runs = []
    for name, title, sub in EVAL_RUNS:
        agg = json.loads((REPO / "04_eval" / "results" / name).read_text(encoding="utf-8"))["aggregate"]
        ver, comp = agg["layers"]["verification"]["score"], agg["composite_score"]
        runs.append((title, sub, ver["mean"], ver["std"] or 0.0, comp["mean"], comp["std"] or 0.0))
    W, left, right, top, bar_h, gap, row_h = 640, 196, 596, 44, 12, 3, 48
    scale = (right - left) / 100
    H = top + row_h * len(runs) + 22
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="{FONT}" role="img" '
           f'aria-label="Verification and composite scores by verifier configuration">']
    out.append(_legend(left, 16, [("Verification layer score", VIOLET), ("Composite score", CYAN)]))
    grid_bottom = top + row_h * len(runs) - 12
    for tick in (0, 25, 50, 75, 100):
        x = left + tick * scale
        out.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{grid_bottom}" stroke="{GRID}" stroke-width="1"/>')
        out.append(_t(x, grid_bottom + 15, tick, 9.5, 500, MUTED, "middle"))
    for i, (title, sub, vm, vs, cm, cs) in enumerate(runs):
        y = top + i * row_h
        out.append(_t(left - 12, y + 11, title, 11, 600, INK, "end"))
        out.append(_t(left - 12, y + 25, sub, 9.5, 400, MUTED, "end"))
        for k, (mean, std, color) in enumerate(((vm, vs, VIOLET), (cm, cs, CYAN))):
            by = y + k * (bar_h + gap)
            out.append(_bar(left, by, mean * scale, bar_h, color))
            end = left + (mean + std) * scale
            if std:
                lo, mid = left + (mean - std) * scale, by + bar_h / 2
                out.append(f'<path d="M{lo:.1f},{mid:.1f}H{end:.1f}M{lo:.1f},{mid - 4:.1f}v8M{end:.1f},{mid - 4:.1f}v8" '
                           f'stroke="{INK}" stroke-width="1.2" fill="none"/>')
            label = f"{mean:.1f}" + (f" ± {std:.1f}" if std else "")
            out.append(_t(end + 6, by + bar_h / 2 + 3.6, label, 10, 700, INK))
    out.append("</svg>")
    return "".join(out)


def render_source() -> list[str]:
    """Write _render.html with the charts in place; return the contents ids in order."""
    snapshot = json.loads((REPO / "01_data" / "demo_snapshot.json").read_text(encoding="utf-8"))
    signals = json.loads((REPO / snapshot["source_signals"]).read_text(encoding="utf-8"))
    page = SOURCE.read_text(encoding="utf-8")
    for marker, svg in (("<!--CHART:releases-->", chart_releases(signals)),
                        ("<!--CHART:tiers-->", chart_tiers(snapshot)), ("<!--CHART:eval-->", chart_eval())):
        if marker not in page:
            raise SystemExit(f"{marker} missing from report.html")
        page = page.replace(marker, svg)
    RENDERED.write_text(page, encoding="utf-8")
    ids = []
    for chunk in page.split('class="pg" data-for="')[1:]:
        ids.append(chunk.split('"', 1)[0])
    return ids


# --- 3. render ------------------------------------------------------------------

READY_JS = """(async () => {
  await Promise.all(['400','500','600','700','800'].map(w => document.fonts.load(w + ' 12px Inter')));
  await Promise.all(['400','600'].map(w => document.fonts.load(w + ' 12px "JetBrains Mono"')));
  await document.fonts.ready;
  const imgs = [...document.images];
  await Promise.all(imgs.map(i => i.complete ? 1 : new Promise(r => { i.onload = i.onerror = r; })));
  return {inter: document.fonts.check('700 12px Inter'), mono: document.fonts.check('400 12px "JetBrains Mono"'),
          broken: imgs.filter(i => !i.naturalWidth).map(i => i.getAttribute('src'))};
})()"""


async def print_pdf(cdp: CDP) -> bytes:
    result = await cdp.send("Page.printToPDF", printBackground=True, preferCSSPageSize=True,
                            displayHeaderFooter=False, generateTaggedPDF=True)
    return base64.b64decode(result["data"])


def contents_pages(pdf: bytes, ids: list[str]) -> dict[str, int]:
    """Page number (1-based) of each contents entry, read from the PDF's own links."""
    doc = fitz.open(stream=pdf, filetype="pdf")
    names = doc.resolve_names() if hasattr(doc, "resolve_names") else {}
    found = []
    for pno in range(min(3, doc.page_count)):
        for link in doc[pno].get_links():
            target = link.get("page", -1)
            if (target is None or target < 0) and link.get("nameddest"):
                target = (names.get(link["nameddest"]) or {}).get("page", -1)
            if target is not None and target >= 0 and link.get("kind") in (fitz.LINK_GOTO, fitz.LINK_NAMED):
                found.append((pno, link["from"].y0, target + 1))
    found.sort()
    if len(found) != len(ids):
        raise SystemExit(f"expected {len(ids)} contents links, found {len(found)}")
    return {i: page for i, (_, _, page) in zip(ids, found)}


# Google Fonts serves a modern browser one variable font for every weight, and
# Chrome can embed a variable font in a PDF only as Type 3 glyph outlines, which
# some viewers render soft. For this legacy user agent it serves one static file
# per weight, which embeds as a real font.
LEGACY_UA = "Mozilla/5.0 (Windows NT 6.1; Trident/7.0; rv:11.0) like Gecko"


async def render(ids: list[str]) -> tuple[bytes, dict[str, int]]:
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/list").read())
    cdp = await CDP.connect(next(t for t in targets if t.get("type") == "page")["webSocketDebuggerUrl"])
    await cdp.send("Emulation.setUserAgentOverride", userAgent=LEGACY_UA)
    await cdp.send("Page.enable")
    await cdp.send("Page.navigate", url=RENDERED.as_uri())
    for _ in range(100):
        if await cdp.js("document.readyState") == "complete":
            break
        await asyncio.sleep(0.2)
    ready = await cdp.js(READY_JS)
    if ready["broken"]:
        raise SystemExit(f"images failed to load: {ready['broken']}")
    if not (ready["inter"] and ready["mono"]):
        print("  ! web fonts did not load (offline?); falling back to system fonts")
    first = await print_pdf(cdp)
    pages = contents_pages(first, ids)
    await cdp.js("(m => { for (const [id, n] of Object.entries(m))"
                 " document.querySelector(`.pg[data-for=\"${id}\"]`).textContent = n; })(%s)" % json.dumps(pages))
    final = await print_pdf(cdp)
    check = contents_pages(final, ids)
    if check != pages:
        raise SystemExit("contents page numbers moved between passes")
    cdp.reader.cancel()
    return final, pages


def run_chrome(ids: list[str]) -> tuple[bytes, dict[str, int]]:
    chrome = next((c for c in CHROME_CANDIDATES if Path(c).is_file()), None)
    if not chrome:
        raise SystemExit("Chrome or Edge not found")
    profile = tempfile.mkdtemp(prefix="report-build-")
    proc = subprocess.Popen([chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
                             f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                             "--disable-extensions", "--allow-file-access-from-files", "about:blank"],
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
        return asyncio.run(render(ids))
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


# --- 4. finish ------------------------------------------------------------------

def finish(pdf: bytes, pages: dict[str, int]) -> None:
    doc = fitz.open(stream=pdf, filetype="pdf")
    source = SOURCE.read_text(encoding="utf-8")
    toc = [[1, "Cover", 1], [1, "Contents", 2]]
    for entry in source.split('<a class="l')[1:]:
        level = int(entry[0])
        target = entry.split('data-for="', 1)[1].split('"', 1)[0]
        number = entry.split('<span class="no">', 1)[1].split("</span>", 1)[0]
        title = entry.split('<span class="tt">', 1)[1].split("</span>", 1)[0]
        label = html.unescape(f"{number} {title}".strip())
        toc.append([level, label, pages[target]])
    doc.set_toc(toc)
    doc.set_metadata({**doc.metadata, **METADATA})
    doc.save(OUTPUT, garbage=4, deflate=True)
    size = OUTPUT.stat().st_size / 1e6
    print(f"  wrote {OUTPUT.relative_to(REPO)}: {doc.page_count} pages, {size:.1f} MB")


def main() -> None:
    prepare_figures()
    ids = render_source()
    try:
        pdf, pages = run_chrome(ids)
    finally:
        RENDERED.unlink(missing_ok=True)
    finish(pdf, pages)


if __name__ == "__main__":
    main()
