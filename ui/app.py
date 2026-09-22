"""SkillRadar AI — a story-led Streamlit interface over the existing backend."""

from __future__ import annotations

import streamlit as st

from ui_adapter import BACKEND, backend_ready, load_recorded_run
from ui_components import brand, inject_css, pipeline
from ui_pages import curriculum, decision, evaluation, gap, go, home, how_it_works, radar, trend_story


st.set_page_config(
    page_title="SkillRadar AI · Know what to teach next",
    page_icon=":material/radar:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PAGES = ["Home", "Radar", "Trend story", "Curriculum", "The gap", "Evaluation", "Decision", "How it works"]
STAGES = {"Home": "Discover", "Radar": "Discover", "Trend story": "Verify",
          "Curriculum": "Compare", "The gap": "Compare", "Evaluation": "Evaluate",
          "Decision": "Decide", "How it works": None}


@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def recorded_data():
    return load_recorded_run()


def navigation() -> None:
    with st.container(horizontal=True):
        for page, icon in (
            ("Home", "home"), ("Radar", "radar"), ("Trend story", "auto_stories"),
            ("Curriculum", "school"), ("The gap", "difference"),
            ("Evaluation", "analytics"), ("Decision", "tips_and_updates"),
            ("How it works", "help_outline"),
        ):
            st.button(page, icon=f":material/{icon}:", key=f"nav_{page}",
                      type="primary" if st.session_state["page"] == page else "secondary",
                      on_click=go, args=(page,))


def main() -> None:
    st.session_state.setdefault("page", "Home")
    st.session_state.setdefault("selected_trend", 0)
    query_trend = st.query_params.get("trend")
    if query_trend is not None:
        try:
            st.session_state["selected_trend"] = int(query_trend)
            st.session_state["page"] = "Trend story"
        except (TypeError, ValueError):
            pass
        st.query_params.clear()
    inject_css()
    brand()
    navigation()
    pipeline(STAGES.get(st.session_state["page"]))

    if not backend_ready():
        st.error(f"AI Trend Agent backend not found at {BACKEND}. Set SKILLRADAR_BACKEND to the existing checkout and restart the app.")
        return
    try:
        snapshot, signals = recorded_data()
    except (ImportError, FileNotFoundError, OSError, ValueError, SystemExit):
        st.error("The recorded run could not be loaded. Check the backend path and saved snapshot files.")
        return
    records = snapshot.get("recommendations") or []
    routes = {
        "Home": lambda: home(snapshot, records, signals),
        "Radar": lambda: radar(records, signals),
        "Trend story": lambda: trend_story(records, signals),
        "Curriculum": lambda: curriculum(records),
        "The gap": lambda: gap(records),
        "Evaluation": lambda: evaluation(records, signals),
        "Decision": lambda: decision(records, signals),
        "How it works": lambda: how_it_works(snapshot),
    }
    routes[st.session_state["page"]]()
    st.caption("SkillRadar AI · Recorded pipeline replay · No external API calls · Backend agents and evaluation artifacts remain unchanged")


if __name__ == "__main__":
    main()
