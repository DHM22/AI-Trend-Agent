"""
FastAPI service -- serves pipeline output as JSON.
==================================================
Read-only. This process makes ZERO API calls and runs no agents: it reads a
captured snapshot written by 02_src/demo_snapshot.py --capture. Producing a
snapshot is the pipeline's job, serving it is this file's job, and keeping
those separate is what lets the frontend work while the agents are still
moving (and while the OpenAI spend limit is blocking live runs).

    uvicorn app:app --reload
    http://127.0.0.1:8000/docs

Point it at a different capture without editing code:

    $env:SNAPSHOT_PATH = "01_data/experiment.json"

RESPONSE SHAPE: every recommendation is exactly Recommendation.to_dict() --
not a copy of it. schemas.py owns that contract and says in so many words not
to duplicate the definitions, because a copy goes stale the moment someone
adds a field and the resulting bug is miserable to trace. So there are no
pydantic mirrors of the dataclasses here. The cost is that /docs shows loose
object schemas; the benefit is that a schemas.py change reaches the API for
free. Do not "fix" this by re-declaring the fields.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import get_args

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

_SRC = str(Path(__file__).resolve().parent / "02_src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from clustering import cluster_signals, load_signals  # noqa: E402
from demo_snapshot import TIER_LABEL, TIER_ORDER, load_snapshot  # noqa: E402
from schemas import ActionTier  # noqa: E402

DEFAULT_SNAPSHOT = "01_data/demo_snapshot.json"
TIERS = list(get_args(ActionTier))

app = FastAPI(
    title="AI Trend Agent",
    description="Evidence-backed curriculum recommendations. The agent only "
                "recommends -- a human approves.",
    version="1.0.0",
)

# The UI is served from somewhere else during development (vite/live-server on
# another port), so browsers block the fetch without this. Wide open on
# purpose: read-only local demo service, nothing here is private.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# SNAPSHOT ACCESS
# Cached on mtime, not forever: re-capturing while the server is up should
# show through on the next request instead of needing a restart.
# ---------------------------------------------------------------------------

_cache: dict[str, object] = {"path": None, "mtime": None, "data": None}


def snapshot_path() -> Path:
    return Path(os.environ.get("SNAPSHOT_PATH", DEFAULT_SNAPSHOT))


def get_snapshot() -> dict:
    p = snapshot_path()
    if not p.exists():
        # 503 rather than 404: the route is fine, the data behind it is not
        # there yet. Says what to run instead of just failing.
        raise HTTPException(
            status_code=503,
            detail=f"no snapshot at {p} -- run: python 02_src/demo_snapshot.py "
                   f"--capture (or set SNAPSHOT_PATH to an existing capture)",
        )

    mtime = p.stat().st_mtime
    if _cache["path"] != str(p) or _cache["mtime"] != mtime:
        _cache.update(path=str(p), mtime=mtime, data=load_snapshot(str(p)))
    return _cache["data"]  # type: ignore[return-value]


def sort_key(rec: dict):
    """
    Order the way a curriculum lead reads it: most urgent tier first, then
    hardest evidence first inside the tier. Mirrors the CLI's ordering so the
    API and the terminal demo cannot disagree about what is 'top'.
    """
    tier = rec.get("recommended_action", "")
    rank = TIER_ORDER.index(tier) if tier in TIER_ORDER else len(TIER_ORDER)
    return (rank, -(rec.get("total_score") or 0))


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
def health():
    """Liveness plus whether the snapshot behind it is actually readable."""
    p = snapshot_path()
    if not p.exists():
        return {"status": "degraded", "snapshot": str(p), "snapshot_found": False}

    snap = get_snapshot()
    return {
        "status": "ok",
        "snapshot": str(p),
        "snapshot_found": True,
        "captured_at": snap.get("captured_at"),
        "recommendations": len(snap.get("recommendations", [])),
    }


@app.get("/run", tags=["pipeline"])
def run():
    """
    The whole captured run: pipeline counts plus every recommendation.
    Named /run because that is what it is -- one recorded execution.
    """
    snap = get_snapshot()
    return {**snap,
            "recommendations": sorted(snap.get("recommendations", []), key=sort_key)}


@app.get("/summary", tags=["pipeline"])
def summary():
    """
    The funnel, for the header of a dashboard: how many signals went in, how
    much survived each narrowing, and the tier breakdown. Cheap to poll.
    """
    snap = get_snapshot()
    recs = snap.get("recommendations", [])
    counts = snap.get("tier_counts", {})

    return {
        "captured_at": snap.get("captured_at"),
        "source_signals": snap.get("source_signals"),
        "funnel": {
            "signals": snap.get("signals_in_file"),
            "clusters": snap.get("clusters_total"),
            "evaluated": snap.get("clusters_processed"),
            "recommendations": len(recs),
            "duplicates_collapsed": snap.get("duplicates_collapsed", 0),
        },
        # TIER_ORDER, so the UI can render it without re-sorting
        "tier_counts": [
            {"tier": t, "label": TIER_LABEL.get(t, t), "count": counts[t]}
            for t in TIER_ORDER if t in counts
        ],
        "actionable": sum(1 for r in recs if r.get("recommended_action") != "watch"),
    }


@app.get("/recommendations", tags=["pipeline"])
def recommendations(
    tier: str | None = Query(None, description=f"one of: {', '.join(TIERS)}"),
    week: int | None = Query(None, description="curriculum week of the cited material"),
    content_type: str | None = Query(None, description="'lab' or 'slides'"),
    min_score: float | None = Query(None, ge=0, le=5, description="total_score floor"),
    actionable: bool = Query(False, description="drop 'watch' items"),
    limit: int | None = Query(None, ge=1, description="return at most this many"),
):
    """
    Filtered view. Filters combine with AND. `index` on each item is its
    position in the unfiltered snapshot, so /recommendations/{index} stays
    valid no matter how the list was filtered to find it.
    """
    if tier is not None and tier not in TIERS:
        raise HTTPException(400, f"unknown tier '{tier}' -- expected one of {TIERS}")
    if content_type is not None and content_type not in ("lab", "slides"):
        raise HTTPException(400, "content_type must be 'lab' or 'slides'")

    all_recs = get_snapshot().get("recommendations", [])
    out = []
    for i, r in enumerate(all_recs):
        match = r.get("match") or {}
        if tier is not None and r.get("recommended_action") != tier:
            continue
        if actionable and r.get("recommended_action") == "watch":
            continue
        # week/content_type describe the CITATION, so an unmatched trend can
        # never satisfy them -- filtering on them drops 'watch' items that
        # never reached the curriculum stage. That is intended.
        if week is not None and match.get("week") != week:
            continue
        if content_type is not None and match.get("content_type") != content_type:
            continue
        if min_score is not None and (r.get("total_score") or 0) < min_score:
            continue
        out.append({**r, "index": i})

    out.sort(key=sort_key)
    if limit is not None:
        out = out[:limit]

    return {
        "count": len(out),
        "total": len(all_recs),
        "filters": {"tier": tier, "week": week, "content_type": content_type,
                    "min_score": min_score, "actionable": actionable},
        "recommendations": out,
    }


@app.get("/recommendations/{index}", tags=["pipeline"])
def recommendation(index: int):
    """One recommendation by its position in the unfiltered snapshot."""
    recs = get_snapshot().get("recommendations", [])
    if index < 0 or index >= len(recs):
        raise HTTPException(404, f"no recommendation at index {index} "
                                 f"(snapshot holds {len(recs)})")
    return {**recs[index], "index": index}


@app.get("/tiers", tags=["meta"])
def tiers():
    """
    The controlled vocabulary, straight from schemas.ActionTier, in the order
    the UI should display it. Saves the frontend hardcoding five strings that
    schemas.py owns.
    """
    return [{"tier": t, "label": TIER_LABEL.get(t, t)} for t in TIER_ORDER]


DEFAULT_WALKTHROUGH = "01_data/walkthrough.json"
_RESULTS_DIR = Path(__file__).resolve().parent / "04_eval" / "results"
_RESULT_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.json$")


@app.get("/walkthrough", tags=["presentation"])
def walkthrough():
    """
    The presenter walkthrough's AUTHORED content: narration, which
    recommendation to feature, and the review findings. Every fact about the
    featured recommendation is read from the snapshot by the page, never from
    this file. Point elsewhere with WALKTHROUGH_PATH.
    """
    p = Path(os.environ.get("WALKTHROUGH_PATH", DEFAULT_WALKTHROUGH))
    if not p.is_file():
        raise HTTPException(404, f"no walkthrough file at {p} -- the walkthrough page "
                                 f"needs it (see 01_data/walkthrough.json)")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"{p} is not valid JSON: {e}")


@app.get("/eval/results/{name}", tags=["presentation"])
def eval_result(name: str):
    """One saved eval run from 04_eval/results/, by exact file name. Read-only;
    names are restricted to plain file names so nothing outside that folder
    can be requested."""
    if not _RESULT_NAME.match(name):
        raise HTTPException(400, "result name must be a plain *.json file name")
    p = _RESULTS_DIR / name
    if not p.is_file():
        raise HTTPException(404, f"no eval result named {name}")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/signals", tags=["pipeline"])
def signals():
    """
    The raw signals the snapshot was captured from, plus how clustering groups
    them. Feeds the Monitoring and Clustering views in ui3.

    Clustering is RE-RUN here, not read from the snapshot (the snapshot only
    stores the count). It is pure Python -- no agent, no API call -- but code
    can change after a capture, so `clusters_match_snapshot` says whether this
    grouping still reproduces the recorded clusters_total. The UI shows it.
    """
    snap = get_snapshot()
    src = Path(snap.get("source_signals") or "")
    if not src.is_file():
        raise HTTPException(404, f"source signals file '{src}' not found")

    raw = load_signals(str(src))
    index = {id(s): i for i, s in enumerate(raw)}
    clusters = cluster_signals(raw)
    return {
        "source": src.as_posix(),
        "signals": [{"title": s.title, "source": s.source,
                     "source_tier": s.source_tier, "published": s.published,
                     "url": s.url, "summary": s.summary}
                    for s in raw],
        "clusters": [{"title": c.representative_title,
                      "members": [index[id(s)] for s in c.signals]}
                     for c in clusters],
        "clusters_match_snapshot": len(clusters) == snap.get("clusters_total"),
    }


# ---------------------------------------------------------------------------
# DASHBOARD
# Mounted LAST: a mount swallows every path beneath it, so mounting at "/"
# would shadow the routes above. /ui keeps them separate, and serving the page
# from this same process means the dashboard and the JSON share an origin --
# no CORS, one command to start, and /chat lands here when the Instructor
# Companion Agent is built.
# ---------------------------------------------------------------------------

_UI = Path(__file__).resolve().parent / "ui"
if _UI.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_UI), html=True), name="ui")

# The onboarding prototype (ui2/) is a SEPARATE mount on a distinct prefix, so
# it cannot shadow /ui or the JSON routes. It is static files only: every
# screen in it is simulated, it reads nothing from this API, and serving it
# here just gives it the same origin as the real dashboard it hands off to.
# Removing the folder removes the feature -- nothing above depends on it.
_UI2 = Path(__file__).resolve().parent / "ui2"
if _UI2.is_dir():
    app.mount("/ui2", StaticFiles(directory=str(_UI2), html=True), name="ui2")

_UI3 = Path(__file__).resolve().parent / "ui3"
if _UI3.is_dir():
    app.mount("/ui3", StaticFiles(directory=str(_UI3), html=True), name="ui3")


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/ui/" if _UI.is_dir() else "/docs")
