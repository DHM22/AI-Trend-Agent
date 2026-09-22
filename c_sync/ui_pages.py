"""Story-led pages for the SkillRadar AI offline presentation."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse

import streamlit as st

from ui_adapter import evaluate_record, extract_upload
from ui_components import (
    action_label, action_tone, e, empty_state, page_intro, pill, radar_art,
    score_ring, section, stat, trend_card,
)
from ui_visuals import radar_map


def go(page: str, selected: int | None = None) -> None:
    st.session_state["page"] = page
    if selected is not None:
        st.session_state["selected_trend"] = selected


def selected_index(records: list[dict]) -> int:
    value = st.session_state.get("selected_trend", 0)
    return value if isinstance(value, int) and 0 <= value < len(records) else 0


def choose_trend(records: list[dict], page: str) -> tuple[int, dict]:
    key = f"trend_selector_{page}"
    st.session_state[key] = selected_index(records)

    def changed() -> None:
        st.session_state["selected_trend"] = st.session_state[key]

    index = st.selectbox("Choose a recorded trend", range(len(records)),
                         format_func=lambda i: records[i].get("trend", "Untitled"),
                         key=key, on_change=changed)
    return index, records[index]


def source_link(value: str) -> None:
    parsed = urlparse(value or "")
    if parsed.scheme in {"https", "http"} and parsed.netloc:
        st.link_button("Open source", value, icon=":material/open_in_new:")


def evidence_cards(record: dict) -> None:
    items = record.get("evidence") or []
    if not items:
        empty_state("No verification evidence saved", "The recorded run does not include source notes for this trend.")
        return
    for index, item in enumerate(items, 1):
        with st.container(border=True):
            st.caption(f"SOURCE {index:02d} · {str(item.get('tier') or 'Tier unavailable').upper()}")
            st.markdown(f"**{item.get('source') or 'Unnamed source'}**")
            st.write(item.get("note") or "No source note recorded.")
            source_link(item.get("url") or item.get("source") or "")


def match_details(match: dict | None) -> None:
    if not match:
        empty_state("No saved curriculum match", "A missing match alone does not prove the course has a gap.")
        return
    sim_pill = (pill(f"Similarity {match['similarity']:.3f}", "violet")
                if isinstance(match.get("similarity"), (int, float)) else "")
    st.html(f'<div class="sr-glass"><div class="sr-kicker">MATCHED COURSE MATERIAL</div><div class="sr-card-title">{e(match.get("citation") or "Citation unavailable")}</div><div class="sr-card-copy">{e(match.get("topic") or "Topic unavailable")}</div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:16px">{pill(str(match.get("content_type") or "Unknown"),"cyan")}{pill("Exact identifier: " + str(match["exact_match"]),"green") if match.get("exact_match") else ""}{sim_pill}</div></div>')
    with st.expander("Read the cited course content", icon=":material/description:"):
        st.caption(match.get("source_file") or "Source file unavailable")
        st.code(match.get("matched_text") or "No excerpt saved.", language=None)


def run_current(record: dict, signals: list, selected: int) -> None:
    with st.spinner("Evaluating curriculum impact and preparing a recommendation..."):
        try:
            evaluation, recommendation = evaluate_record(record, signals)
            st.session_state["evaluation"] = (selected, evaluation, recommendation)
        except Exception:
            st.error("The current agents could not complete this offline run. Check the backend installation and recorded data.")


@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def maturity_scores(records: list[dict], signals: list) -> list[int | None]:
    """Use the original Evaluation Agent for every radar maturity badge."""
    scores = []
    for record in records:
        try:
            evaluation, _ = evaluate_record(record, signals)
            scores.append(evaluation.maturity_score)
        except Exception:
            scores.append(None)
    return scores


def home(snapshot: dict, records: list[dict], signals: list) -> None:
    left, right = st.columns([1.08, 0.92], gap="large", vertical_alignment="center")
    with left:
        st.html('<div class="sr-eyebrow">THE FUTURE OF CURRICULUM INTELLIGENCE</div><div class="sr-hero-title">SkillRadar <span class="sr-gradient">AI</span></div><div style="font-size:clamp(1.75rem,3vw,2.7rem);font-weight:750;letter-spacing:-.05em;color:#fff;margin-bottom:18px">Know what to teach next.</div><p class="sr-hero-copy">SkillRadar AI watches the technology landscape, detects meaningful trends, compares them with your curriculum, and recommends what should change.</p>')
        with st.container(horizontal=True):
            st.button("Explore the radar", type="primary", icon=":material/radar:",
                      on_click=go, args=("Radar",))
            st.button("See how it works", icon=":material/arrow_forward:",
                      on_click=go, args=("How it works",))
    with right:
        radar_art()
    section("From noise to curriculum action.",
            "A recorded run shows how source signals become a focused list of curriculum decisions.",
            "THE BIG PICTURE")
    counts = [
        (snapshot.get("signals_in_file", len(signals)), "Source signals", "01 · DISCOVER"),
        (snapshot.get("clusters_total", "—"), "Trend clusters", "02 · GROUP"),
        (snapshot.get("clusters_processed", "—"), "Trends assessed", "03 · VERIFY"),
        (len(records), "Recommendations", "04 · DECIDE"),
    ]
    cols = st.columns(4, gap="medium")
    for col, (value, name, kicker) in zip(cols, counts):
        with col:
            stat(value, name, kicker)
    st.caption(f"Recorded on {snapshot.get('captured_at', 'an unavailable date')}. These are saved pipeline counts, not live monitoring totals.")
    section("A decision you can trace.",
            "Start with a technology signal, inspect the evidence, then see exactly which course area may need attention.",
            "WHY IT MATTERS")
    if records:
        featured = next((r for r in records if r.get("recommended_action") == "add_new_lesson"), records[0])
        index = records.index(featured)
        left, right = st.columns([1.1, 0.9], gap="large")
        with left:
            trend_card(featured)
            st.button("Follow this trend's story", type="primary", icon=":material/arrow_forward:",
                      key="featured_story", on_click=go, args=("Trend story", index))
        with right:
            st.html('<div class="sr-glass"><div class="sr-kicker">THE SKILLRADAR JOURNEY</div><div class="sr-card-title" style="font-size:1.65rem">From source to decision</div><p class="sr-card-copy" style="display:block;min-height:0">Each saved action carries verification evidence and a total evaluation score. Course citations appear where a match was found.</p><div style="margin-top:22px;line-height:2.2;color:#d4def0">Discover <span style="color:#7ed6e9">→</span> Verify <span style="color:#7ed6e9">→</span> Compare <span style="color:#7ed6e9">→</span> Evaluate <span style="color:#7ed6e9">→</span> Decide</div></div>')


def radar(records: list[dict], signals: list) -> None:
    page_intro("01 / DISCOVER", "Technology radar", "Explore the recorded trends. Each light is an assessed technology signal; select one to follow its story.")
    if not records:
        empty_state("The radar is quiet", "No trends are saved in the current recorded run.")
        return
    search_col, filter_col = st.columns([2, 1])
    with search_col:
        search = st.text_input("Find a trend", placeholder="Search by technology or source", icon=":material/search:")
    with filter_col:
        actions = ["All decisions"] + sorted({r.get("recommended_action", "") for r in records})
        action = st.selectbox("Filter by decision", actions,
                              format_func=lambda a: a if a == "All decisions" else action_label(a))
    visible = [(i, r) for i, r in enumerate(records) if
               (not search or search.lower() in (r.get("trend", "") + " " + " ".join(
                   str(item.get("source") or "") for item in r.get("evidence") or [])).lower()) and
               (action == "All decisions" or r.get("recommended_action") == action)]
    st.caption(f"{len(visible)} of {len(records)} recorded trends · Node size reflects current agent maturity · Glow reflects saved confidence · Color reflects the saved action")
    if not visible:
        empty_state("No trends found", "Try another search or decision filter.")
        return
    maturity = maturity_scores(records, signals)
    radar_map(visible, maturity)
    section("Signals worth a closer look", "Open a trend to inspect its source evidence and curriculum impact.", "RECORDED TRENDS")
    for offset in range(0, len(visible), 2):
        cols = st.columns(2, gap="medium")
        for col, pair in zip(cols, visible[offset:offset + 2]):
            index, record = pair
            with col:
                trend_card(record, index == selected_index(records), maturity[index])
                st.button("Open trend story", key=f"radar_card_{index}", icon=":material/arrow_forward:",
                          on_click=go, args=("Trend story", index))


def trend_story(records: list[dict], signals: list) -> None:
    page_intro("02 / VERIFY", "Why is this trending?", "Follow one recorded trend from its original signal to the evidence used for verification.")
    if not records:
        empty_state("No trend selected", "The recorded run has no trends to inspect.")
        return
    selected, record = choose_trend(records, "story")
    left, right = st.columns([1.45, 0.55], gap="large")
    with left:
        st.html(f'<div class="sr-glass"><div class="sr-kicker">TECHNOLOGY TREND</div><div class="sr-card-title" style="font-size:clamp(1.7rem,3vw,2.7rem)">{e(record.get("trend"))}</div><p style="color:#c2d0e1;font-size:1.05rem">{e(record.get("verification_note") or "No verification note recorded.")}</p></div>')
    with right:
        confidence = record.get("confidence")
        stat(f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "—", "Recorded confidence", "VERIFICATION")
        st.caption(f"{len(record.get('evidence') or [])} saved verification evidence item(s)")
    section("The signal trail", "Original monitoring signals are shown by published date when that date was recorded.", "WHAT WE SAW")
    originals = sorted((s for s in signals if s.title == record.get("trend")), key=lambda s: s.published or "")
    if originals:
        items = "".join(f'<div class="sr-timeline-item"><div class="sr-kicker">{e(s.published or "DATE UNAVAILABLE")} · {e(s.source_tier)}</div><div class="sr-card-title">{e(s.source)}</div><div class="sr-card-copy" style="display:block;min-height:0">{e((s.summary or "No summary recorded.")[:280])}</div></div>' for s in originals)
        st.html(f'<div class="sr-timeline">{items}</div>')
        for signal in originals:
            source_link(signal.url)
    else:
        empty_state("Original signal unavailable", "The saved signal file has no exact title match for this recorded trend.")
    section("The verification evidence", "These are the source notes saved by the Verification Agent. Some sources have no date in the snapshot.", "WHY WE TRUST IT")
    evidence_cards(record)
    section("Should this affect the curriculum?", "Next, compare this trend with the saved curriculum match.", "NEXT STEP")
    st.button("Check the curriculum", type="primary", icon=":material/arrow_forward:",
              on_click=go, args=("The gap", selected))


def curriculum(records: list[dict]) -> None:
    page_intro("03 / COMPARE", "Your curriculum, made visible.",
               "Explore course areas cited by the recorded run, or upload material for a local content preview.")
    matches = [r["match"] for r in records if r.get("match")]
    section("Where the current run found material", "This timeline contains only weeks cited in saved matches. It is not a full course audit.", "COURSE MAP")
    if matches:
        by_week: dict[int | None, set[str]] = defaultdict(set)
        for match in matches:
            by_week[match.get("week")].add(match.get("topic") or "Untitled topic")
        weeks = sorted(by_week, key=lambda value: (value is None, value or 0))
        for offset in range(0, len(weeks), 4):
            cols = st.columns(min(4, len(weeks) - offset), gap="medium")
            for col, week in zip(cols, weeks[offset:offset + 4]):
                with col:
                    title = f"Week {week:02d}" if isinstance(week, int) else "Uncategorised"
                    topics = sorted(by_week[week])
                    st.html(f'<div class="sr-glass"><div class="sr-kicker">CITED COURSE AREA</div><div class="sr-card-title">{e(title)}</div><div class="sr-card-copy" style="display:block;min-height:0">{e(" · ".join(topics))}</div><div style="margin-top:18px">{pill(f"{len(topics)} topic(s)","cyan")}</div></div>')
    else:
        empty_state("No course areas cited", "The recorded recommendations did not include a curriculum match.")
    section("Bring your own curriculum", "Preview the text the existing backend can extract from PDF, PowerPoint, or Jupyter notebooks.", "LOCAL PREVIEW")
    st.html('<div class="sr-glass" style="text-align:center"><div style="font-size:2.4rem;color:#a78bfa">⇧</div><div class="sr-card-title" style="font-size:1.6rem">Drop your curriculum here</div><p style="color:#b8c6d9">PDF · PPTX · Notebook</p></div>')
    uploaded = st.file_uploader("Choose a course file", type=["pdf", "pptx", "ipynb"])
    st.caption("Local preview only. An upload is not indexed or compared with trends in this interface.")
    if uploaded and st.button("Extract course content", type="primary", icon=":material/document_scanner:"):
        with st.spinner("Reading your curriculum..."):
            try:
                chunks = extract_upload(uploaded.name, uploaded.getvalue())
                st.session_state["curriculum_upload"] = (uploaded.name, chunks)
            except Exception:
                st.error("This file could not be processed. Check its format and the installed UI dependencies.")
    saved = st.session_state.get("curriculum_upload")
    if saved:
        name, chunks = saved
        section(f"{len(chunks)} sections extracted", f"From {name}. This is a local preview, not a curriculum coverage score.", "UPLOAD RESULT")
        topics = sorted({chunk.topic for chunk in chunks})
        st.write("**Topics found:** " + (" · ".join(topics) if topics else "None"))
        for chunk in chunks[:10]:
            with st.expander(chunk.citation, icon=":material/description:"):
                st.write(chunk.text)
        if len(chunks) > 10:
            st.caption(f"Showing the first 10 of {len(chunks)} sections.")


def gap(records: list[dict]) -> None:
    page_intro("03 / COMPARE", "Is this trend already taught?", "Place the recorded trend beside the course material the Curriculum Agent found.")
    if not records:
        empty_state("No trend to compare", "The recorded run has no trend data.")
        return
    selected, record = choose_trend(records, "gap")
    match = record.get("match")
    left, right = st.columns(2, gap="large")
    with left:
        st.html(f'<div class="sr-glass sr-compare"><div class="sr-compare-label">TECHNOLOGY TREND</div><div class="sr-compare-title">{e(record.get("trend"))}</div><div class="sr-compare-text">{e(record.get("verification_note") or "No verification note recorded.")}</div></div>')
    with right:
        if match:
            st.html(f'<div class="sr-glass sr-compare"><div class="sr-compare-label">CURRENT COURSE MATERIAL</div><div class="sr-compare-title">{e(match.get("citation") or "Citation unavailable")}</div><div class="sr-compare-text">{e((match.get("matched_text") or "No excerpt saved.")[:260])}</div></div>')
        else:
            st.html('<div class="sr-glass sr-compare"><div class="sr-compare-label">CURRENT COURSE MATERIAL</div><div class="sr-compare-title">No match saved</div><div class="sr-compare-text">The recorded run contains no cited slide or notebook cell for this trend.</div></div>')
    action = record.get("recommended_action", "")
    if action == "add_new_lesson" and not match:
        reveal, tone, detail = "Curriculum gap identified", "", "The saved Recommendation Agent proposed a new lesson after the curriculum check."
    elif match:
        reveal, tone, detail = "Related material found", "green", "A saved course citation links this trend to existing material. The recorded action explains what should change."
    else:
        reveal, tone, detail = "Coverage not established", "amber", "No saved match exists, but the recorded agent did not recommend a new lesson. This is not presented as a confirmed gap."
    st.html(f'<div class="sr-reveal {tone}">{e(reveal)}</div>')
    st.caption(detail)
    if match:
        section("The specific course reference", "Inspect the citation used by the backend.", "MATCH DETAIL")
        match_details(match)
    st.button("See the evaluation", type="primary", icon=":material/arrow_forward:",
              on_click=go, args=("Evaluation", selected))


def evaluation(records: list[dict], signals: list) -> None:
    page_intro("04 / EVALUATE", "How important is this?", "The original Evaluation Agent scores maturity and course relevance. The interface only displays its returned numbers.")
    if not records:
        empty_state("Nothing to evaluate", "No trends are available in the recorded run.")
        return
    selected, record = choose_trend(records, "evaluation")
    st.html(f'<div class="sr-glass"><div class="sr-kicker">CURRENT TREND</div><div class="sr-card-title">{e(record.get("trend"))}</div><div class="sr-card-copy" style="display:block;min-height:0">{e(record.get("verification_note") or "No verification note recorded.")}</div></div>')
    if st.button("Run the Evaluation Agent", type="primary", icon=":material/play_arrow:"):
        run_current(record, signals, selected)
    saved = st.session_state.get("evaluation")
    if not saved or saved[0] != selected:
        empty_state("Ready to evaluate", "Run the existing agent to reveal the maturity, relevance, and overall scores for this recorded trend.")
        return
    result = saved[1]
    section("The agent's assessment", "Scores below come directly from EvaluationAgent.run.", "THE VERDICT")
    cols = st.columns(3, gap="medium")
    for col, title, value, color in zip(cols,
                                         ("MATURITY", "RELEVANCE", "OVERALL"),
                                         (result.maturity_score, result.relevance_score, result.total_score),
                                         ("#a78bfa", "#67e8f9", "#34d399")):
        with col:
            score_ring(title, value, color)
    section("Why did SkillRadar reach this conclusion?", "The explanation comes from the Evaluation Agent's validated offline fallback.", "AI INSIGHT")
    st.html(f'<div class="sr-glass selected"><div class="sr-kicker">✦ EVALUATION RATIONALE</div><p style="font-size:1.12rem;color:#e4eaf8;line-height:1.7;margin:15px 0 0">{e(result.rationale)}</p></div>')
    if record.get("total_score") != result.total_score:
        st.warning("This current agent score differs from the older recorded total. The saved run may have used an earlier backend version.")
    section("Evidence used", "The score is grounded in recorded verification and curriculum evidence.", "TRACEABILITY")
    match_details(record.get("match"))
    with st.expander("Verification sources", icon=":material/fact_check:"):
        evidence_cards(record)
    st.button("See the recommended action", type="primary", icon=":material/arrow_forward:",
              on_click=go, args=("Decision", selected))


def decision(records: list[dict], signals: list) -> None:
    page_intro("05 / DECIDE", "What should we do?", "A specific curriculum action, with its reason and supporting evidence close at hand.")
    if not records:
        empty_state("No decision recorded", "The saved run has no recommendations.")
        return
    selected, record = choose_trend(records, "decision")
    action = record.get("recommended_action", "")
    tone = "green" if action == "add_new_lesson" else "amber" if action == "watch" else ""
    match = record.get("match")
    area = match.get("citation") if match else "No cited course area"
    ev_pill = pill(f"{len(record.get('evidence') or [])} evidence item(s)", "cyan")
    st.html(f'<div class="sr-decision {tone}"><div class="sr-kicker">RECORDED RECOMMENDATION · {e(record.get("trend"))}</div><div class="sr-decision-title">{e(action_label(action))}</div><div class="sr-decision-copy">{e(record.get("verification_note") or "No verification note recorded.")}</div><div style="margin-top:25px;display:flex;gap:8px;flex-wrap:wrap">{ev_pill}{pill(area,"violet") if match else pill("No cited course area","amber")}</div></div>')
    section("The action plan", "Steps returned by the saved Recommendation Agent run.", "WHAT CHANGES")
    for number, step in enumerate(record.get("action_plan") or [], 1):
        st.html(f'<div class="sr-glass" style="margin-bottom:12px;display:flex;align-items:flex-start;gap:18px"><span class="sr-pill violet">{number:02d}</span><div style="color:#e6edf9;font-size:1.04rem;line-height:1.55">{e(step)}</div></div>')
    section("Why this decision?", "Trace the result back through the recorded pipeline.", "EVIDENCE CHAIN")
    chain = [
        ("Trend", record.get("trend") or "Unavailable"),
        ("Evidence", f"{len(record.get('evidence') or [])} saved item(s)"),
        ("Curriculum", area),
        ("Evaluation", f"Saved total {record.get('total_score')}/5" if record.get("total_score") is not None else "Total unavailable"),
        ("Decision", action_label(action)),
    ]
    flow_arrow = '<div class="sr-flow-arrow">→</div>'
    cells = "".join(f'<div class="sr-flow-item sr-glass"><div class="sr-kicker">{e(title)}</div><div class="sr-card-title" style="font-size:1rem">{e(text)}</div></div>{flow_arrow if i<4 else ""}' for i,(title,text) in enumerate(chain))
    st.html(f'<div class="sr-flow">{cells}</div>')
    with st.expander("Inspect verification evidence", icon=":material/fact_check:"):
        evidence_cards(record)
    saved = st.session_state.get("evaluation")
    if saved and saved[0] == selected:
        current = saved[2]
        with st.expander("Current Recommendation Agent result", icon=":material/neurology:"):
            st.caption("Current offline run; it may differ from the recorded snapshot.")
            st.subheader(action_label(current.recommended_action))
            for step in current.action_plan:
                st.markdown(f"- {step}")
    elif st.button("Run the current agents", icon=":material/play_arrow:"):
        run_current(record, signals, selected)
        st.rerun()


def how_it_works(snapshot: dict) -> None:
    page_intro("THE METHOD", "How does SkillRadar work?", "Five simple steps turn technology noise into curriculum action you can explain.")
    stages = [
        ("01", "Listen", "We watch trusted technology sources for new developments.", "sensors"),
        ("02", "Verify", "We check the evidence before treating a signal as meaningful.", "verified"),
        ("03", "Compare", "We look for related slides and labs in the curriculum.", "difference"),
        ("04", "Evaluate", "We measure how established the trend is and how strongly it connects to current material.", "analytics"),
        ("05", "Recommend", "We suggest a specific course action and keep the evidence attached.", "tips_and_updates"),
    ]
    for number, title, copy, icon in stages:
        st.html(f'<div class="sr-glass" style="margin-bottom:14px;display:flex;align-items:center;gap:25px"><div style="font-size:2rem;font-weight:800;color:#a78bfa;min-width:65px">{number}</div><div><div class="sr-card-title" style="margin:0 0 5px;font-size:1.45rem">{e(title)}</div><div style="color:#b7c6da">{e(copy)}</div></div></div>')
    section("Every recommendation has a trail.", "Follow the source, the course match, the agent evaluation, and the final action.", "EXPLAINABLE BY DESIGN")
    st.html(f'<div class="sr-glass selected" style="text-align:center"><div class="sr-metric-number">{e(snapshot.get("signals_in_file", "—"))} → {e(snapshot.get("clusters_total", "—"))} → {e(len(snapshot.get("recommendations") or []))}</div><div class="sr-metric-label">Saved signals → clusters → recommendations in this recorded run</div></div>')
    st.button("Explore the radar", type="primary", icon=":material/radar:", on_click=go, args=("Radar",))
