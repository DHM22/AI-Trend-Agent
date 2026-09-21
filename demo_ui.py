"""
Demo UI -- reads a captured snapshot, renders it for a curriculum lead.
=======================================================================
Read-only. ZERO API calls, no agents, no network, no key required. It reads
the JSON that 02_src/demo_snapshot.py --capture wrote, which is the same
contract app.py serves over HTTP.

    streamlit run demo_ui.py

Point it at a different capture without editing code:

    $env:SNAPSHOT_PATH = "01_data/experiment.json"
    streamlit run demo_ui.py

WHY IT READS THE FILE AND NOT THE API: one less moving part in front of
graders. Nothing to start, nothing to fall over mid-demo. app.py serves the
same data if a networked client ever needs it.

FIELD CONTRACT: every recommendation here is exactly Recommendation.to_dict()
from schemas.py. Field names are NOT duplicated as constants -- if schemas.py
changes, this file should be updated to match, not the other way round.
"""

import json
import os
import sys
from pathlib import Path

import streamlit as st

# trace_view() turns a stored trace into plain words; it lives in the pipeline
# package so test_chain can test it. Importing it runs no agent and no API call.
sys.path.insert(0, str(Path(__file__).resolve().parent / "02_src"))
from demo_snapshot import trace_view  # noqa: E402

DEFAULT_SNAPSHOT = "01_data/demo_snapshot.json"

# Ordered the way a curriculum lead reads it: most urgent first. Mirrors
# TIER_ORDER in demo_snapshot.py so the UI and the CLI cannot disagree about
# what counts as "top".
TIER_ORDER = [
    "update_existing_material",
    "add_new_lesson",
    "add_optional_content",
    "investigate_larger_change",
    "watch",
]

TIER_LABEL = {
    "update_existing_material": "UPDATE EXISTING MATERIAL",
    "add_new_lesson": "ADD NEW LESSON",
    "add_optional_content": "ADD OPTIONAL CONTENT",
    "investigate_larger_change": "INVESTIGATE LARGER CHANGE",
    "watch": "WATCH",
}

TIER_COLOR = {
    "update_existing_material": "#C0392B",   # act now
    "add_new_lesson": "#B9770E",
    "add_optional_content": "#1F7A3D",
    "investigate_larger_change": "#6C3483",
    "watch": "#566573",                      # no action
}


# ---------------------------------------------------------------------------
# LOADING
# ---------------------------------------------------------------------------

def snapshot_path() -> Path:
    return Path(os.environ.get("SNAPSHOT_PATH", DEFAULT_SNAPSHOT))


@st.cache_data(show_spinner=False)
def load_snapshot(path_str: str, mtime: float) -> dict:
    """Cached on (path, mtime), so re-capturing while the UI is open shows
    through on the next rerun instead of needing a restart. mtime is an
    argument purely so the cache key changes when the file does."""
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def tier_badge(tier: str) -> str:
    color = TIER_COLOR.get(tier, "#566573")
    label = TIER_LABEL.get(tier, tier)
    return (f"<span style='background:{color};color:white;padding:3px 10px;"
            f"border-radius:3px;font-size:0.75rem;font-weight:600;"
            f"letter-spacing:0.5px;'>{label}</span>")


def confidence_badge(conf) -> str:
    """Confidence is a verification output, not a quality score -- label it so
    nobody reads 0.4 as 'a bad recommendation' rather than 'a weak claim'."""
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return "<span style='color:#566573;'>confidence n/a</span>"

    if c >= 0.85:
        color, word = "#1F7A3D", "strong"
    elif c >= 0.60:
        color, word = "#B9770E", "moderate"
    else:
        color, word = "#C0392B", "weak"

    return (f"<span style='border:1px solid {color};color:{color};"
            f"padding:2px 8px;border-radius:3px;font-size:0.75rem;"
            f"font-weight:600;'>confidence {c:.2f} · {word}</span>")


# ---------------------------------------------------------------------------
# PAGE
# ---------------------------------------------------------------------------

st.set_page_config(page_title="AI Trend Agent", layout="wide")

st.title("AI Trend Agent")
st.caption("Evidence-backed curriculum recommendations. "
           "The agent only recommends — a human approves.")

path = snapshot_path()

if not path.exists():
    st.error(
        f"No snapshot at `{path}`.\n\n"
        "Capture one first:\n\n"
        "```\npython 02_src/demo_snapshot.py --capture\n```\n\n"
        "Or point `SNAPSHOT_PATH` at an existing capture."
    )
    st.stop()

try:
    snap = load_snapshot(str(path), path.stat().st_mtime)
except (json.JSONDecodeError, UnicodeDecodeError) as e:
    # A capture interrupted mid-write leaves a truncated file. Say what is
    # wrong rather than showing a stack trace to the room.
    st.error(f"`{path}` exists but could not be parsed as JSON: {e}\n\n"
             "The capture may have been interrupted. Re-run it.")
    st.stop()

recs = snap.get("recommendations", [])

# ---- funnel -------------------------------------------------------------
st.subheader("Pipeline")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Signals", snap.get("signals_in_file", "—"))
c2.metric("Clusters", snap.get("clusters_total", "—"))
c3.metric("Evaluated", snap.get("clusters_processed", "—"))
c4.metric("Recommendations", len(recs))
c5.metric("Actionable",
          sum(1 for r in recs if r.get("recommended_action") != "watch"),
          help="Everything that is not 'watch' — i.e. needs a human decision.")

captured = snap.get("captured_at", "")
source = snap.get("source_signals", "")
dupes = snap.get("duplicates_collapsed", 0)

meta = f"Recorded run from `{source}`"
if captured:
    meta += f" · captured {captured[:16].replace('T', ' ')} UTC"
if dupes:
    meta += f" · {dupes} duplicate-citation recommendation(s) merged"
st.caption(meta)

# ---- tier breakdown -----------------------------------------------------
counts = snap.get("tier_counts", {})
if counts:
    st.markdown(
        " ".join(
            f"{tier_badge(t)} <strong>{counts[t]}</strong>"
            for t in TIER_ORDER if t in counts
        ),
        unsafe_allow_html=True,
    )

st.divider()

# ---- filters ------------------------------------------------------------
present_tiers = [t for t in TIER_ORDER
                 if any(r.get("recommended_action") == t for r in recs)]

f1, f2, f3 = st.columns([2, 1, 1])

with f1:
    chosen = st.multiselect(
        "Action tier",
        options=present_tiers,
        default=present_tiers,
        format_func=lambda t: TIER_LABEL.get(t, t),
    )

with f2:
    hide_watch = st.checkbox("Actionable only", value=False,
                             help="Hide 'watch' items.")

with f3:
    min_score = st.slider("Minimum score", 0.0, 5.0, 0.0, 0.5)


def keep(r: dict) -> bool:
    tier = r.get("recommended_action")
    if tier not in chosen:
        return False
    if hide_watch and tier == "watch":
        return False
    if (r.get("total_score") or 0) < min_score:
        return False
    return True


def sort_key(r: dict):
    tier = r.get("recommended_action", "")
    rank = TIER_ORDER.index(tier) if tier in TIER_ORDER else len(TIER_ORDER)
    return (rank, -(r.get("total_score") or 0))


shown = sorted([r for r in recs if keep(r)], key=sort_key)

st.markdown(f"**{len(shown)}** of **{len(recs)}** recommendation(s)")

if not shown:
    st.info("Nothing matches these filters.")
    st.stop()

# ---- cards --------------------------------------------------------------
for r in shown:
    tier = r.get("recommended_action", "")
    match = r.get("match") or {}
    score = r.get("total_score")

    view = trace_view(r)          # None for snapshots captured before traces

    with st.container(border=True):
        head, badge = st.columns([5, 2])
        with head:
            st.markdown(f"**{r.get('trend', 'untitled')}**")
        with badge:
            st.markdown(tier_badge(tier), unsafe_allow_html=True)

        line = confidence_badge(r.get("confidence"))
        if score is not None:
            line += f" &nbsp;&nbsp; <strong>{score}</strong>/5"
        st.markdown(line, unsafe_allow_html=True)

        if match.get("citation"):
            kind = "lab cell" if match.get("content_type") == "lab" else "slide"
            how = (f"exact match on `{match['exact_match']}`"
                   if match.get("exact_match")
                   else f"similarity {match.get('similarity')}")
            st.markdown(f"📎 `{match['citation']}` — {kind}, found by {how}")
        elif view and view["search_failed"]:
            # NEVER shown as "no curriculum match": a search that could not run
            # is not a finding. This stays outside any expander on purpose.
            st.error(f"**{view['failure_banner']}**"
                     + (f"\n\nReason: {view['failure_reason']}" if view["failure_reason"] else ""))
        else:
            # Absence of a citation is information, not an empty field: it is
            # what separates "we searched and found nothing" from "we matched
            # something". The plan says which.
            st.markdown("📎 *no curriculum match*")

        if r.get("action_plan"):
            st.markdown("**Plan**")
            for step in r["action_plan"]:
                st.markdown(f"- {step}")

        # ---- evidence trail ------------------------------------------
        evidence = r.get("evidence") or []
        with st.expander(f"Evidence trail ({len(evidence)} source(s))"):
            if r.get("verification_note"):
                st.markdown(f"*{r['verification_note']}*")

            if not evidence:
                st.markdown("No evidence recorded for this trend.")
            for e in evidence:
                tier_txt = e.get("tier", "?")
                src = e.get("source", "?")
                url = e.get("url", "")
                note = e.get("note", "")

                bits = [f"**[{tier_txt}]** {src}"]
                if note:
                    bits.append(f"— {note}")
                st.markdown(" ".join(bits))
                if url:
                    st.markdown(f"<small>{url}</small>", unsafe_allow_html=True)

            if match.get("matched_text"):
                st.markdown("**Matched curriculum text**")
                st.code(match["matched_text"], language=None)

        # ---- agent trace (collapsed; absent for pre-trace snapshots) ----
        if view:
            with st.expander(view["label"], expanded=False):
                st.markdown("**Verification — is this trend real?**")
                if view["verification_mode"]:
                    st.caption(view["verification_mode"])
                for i, s in enumerate(view["verification_steps"], 1):
                    st.markdown(f"{i}. {s['text']}")
                    if s["why"]:
                        st.caption(f"Why: {s['why']}")
                    if s["detail"]:
                        st.caption(f"→ {s['detail']}")
                if not view["verification_steps"]:
                    st.caption(view["verification_empty"])

                st.markdown("**Curriculum — does it affect what we teach?**")
                if view["search_failed"]:
                    st.error(view["failure_banner"])
                for i, s in enumerate(view["curriculum_steps"], 1):
                    st.markdown(f"{i}. {s['text']}")
                    if s["detail"]:
                        st.caption(f"→ {s['detail']}")
                if not view["curriculum_steps"]:
                    st.caption(view["curriculum_empty"])

                if view["stopped_early"]:
                    st.caption("An agent hit its step limit and was asked to "
                               "conclude early, so this trace may be shorter "
                               "than the reasoning was.")
                if view["conclusion"]:
                    st.markdown("**Conclusion**")
                    st.markdown(view["conclusion"])

st.divider()
st.caption(
    "This is a recorded run, not a live one. The pipeline is non-deterministic "
    "— the same signals can produce different tiers across runs — so the demo "
    "replays a captured snapshot. Live mode is one flag away: "
    "`python 02_src/demo_snapshot.py --capture`."
)
