"""Serve a saved report. No pipeline imports, API keys, or background jobs."""

import json
import os
from datetime import timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import ValidationError

from app.models import Report

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
ACTIONS = {
    "update_existing_material": {"label": "Update material", "description": "Existing lab or slide needs changes", "tone": "amber", "symbol": "↗"},
    "add_optional_content": {"label": "Optional content", "description": "Nice-to-have addition", "tone": "blue", "symbol": "+"},
    "add_new_lesson": {"label": "New lesson", "description": "Topic not covered yet", "tone": "green", "symbol": "+"},
    "watch": {"label": "Watch", "description": "No action needed now", "tone": "gray", "symbol": "◎"},
}
STATS = (
    ("signals_in_file", "Signals in file", "Incoming releases & articles"),
    ("clusters_total", "Clusters total", "Grouped into distinct trends"),
    ("clusters_processed", "Clusters processed", "Reviewed by the pipeline"),
    ("duplicates_collapsed", "Duplicates collapsed", "Repeated recommendations merged"),
)

app = FastAPI(title="Curriculum Trend Monitor", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(env=Environment(
    loader=FileSystemLoader(APP_DIR / "templates"),
    autoescape=select_autoescape(default_for_string=True, default=True),
))


class ReportUnavailable(Exception):
    """A safe, audience-facing report loading failure."""


def reject_nonfinite(value: str):
    raise ValueError(f"Non-finite JSON number: {value}")


def load_report() -> Report:
    path = Path(os.environ.get("REPORT_PATH") or "data/report.json").expanduser()
    if not path.is_absolute():
        path = ROOT / path
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
        return Report.model_validate(data)
    except FileNotFoundError as exc:
        raise ReportUnavailable("The report file hasn’t arrived yet. Please ask the presenter to check the report location, then refresh.") from exc
    except (OSError, UnicodeError) as exc:
        raise ReportUnavailable("We couldn’t read the saved report. Please ask the presenter to check the file, then refresh.") from exc
    except (ValueError, ValidationError, RecursionError) as exc:
        raise ReportUnavailable("The saved report couldn’t be opened because its format is invalid. Please ask the presenter for a valid report, then refresh.") from exc


def evidence_link(evidence: dict) -> str | None:
    """Use a source URL when url is absent; never link executable schemes."""
    candidate = (evidence.get("url") or evidence.get("source") or "").strip()
    try:
        parsed = urlsplit(candidate)
        if parsed.scheme.lower() in {"https", "http"} and parsed.netloc and not any(ord(c) < 32 for c in candidate):
            return candidate
    except ValueError:
        pass
    return None


def dashboard_context(report: Report) -> dict:
    data = report.model_dump()
    rows = sorted(data.get("recommendations") or [], key=lambda row: (
        -(row.get("total_score") if row.get("total_score") is not None else -1),
        -(row.get("confidence") if row.get("confidence") is not None else -1),
    ))
    for row in rows:
        action = row.get("recommended_action")
        row["action"] = ACTIONS.get(action, {"label": "Not specified", "tone": "gray"})
        confidence = row.get("confidence")
        row["confidence_pct"] = round(confidence * 100) if confidence is not None else None
        row["confidence_tone"] = "gray" if confidence is None else "green" if confidence >= .8 else "amber" if confidence >= .5 else "red"
        row["score_label"] = f"{row.get('total_score'):g}" if row.get("total_score") is not None else "—"
        for evidence in row.get("evidence") or []:
            evidence["link"] = evidence_link(evidence)
    captured = report.captured_at
    if captured:
        # Treat timezone-less source timestamps as UTC rather than server local time.
        captured = captured.replace(tzinfo=timezone.utc) if captured.tzinfo is None else captured
        captured_label = captured.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    else:
        captured_label = "Capture time unavailable"
    counts = data.get("tier_counts") or {}
    filters = [{"key": key, **meta, "count": counts.get(key) if counts.get(key) is not None else sum(r.get("recommended_action") == key for r in rows)} for key, meta in ACTIONS.items()]
    return {"report": data, "rows": rows, "filters": filters, "stats": STATS, "captured_label": captured_label, "error": None}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    try:
        context = dashboard_context(load_report())
        status = 200
    except ReportUnavailable as exc:
        context = {"error": str(exc), "rows": [], "report": {}}
        status = 503
    return templates.TemplateResponse(request=request, name="index.html", context=context, status_code=status, headers={"Cache-Control": "no-store"})


@app.get("/api/report", response_model=Report)
def report_api():
    try:
        report = load_report()
    except ReportUnavailable as exc:
        return JSONResponse({"error": str(exc)}, status_code=503, headers={"Cache-Control": "no-store"})
    return JSONResponse(report.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    return {"status": "ok"}
