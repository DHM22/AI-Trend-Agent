"""
Companion agent page for C-Sync.
=================================
Renders what companion_agent's pure functions return. It holds NO analysis
logic of its own: every number, state and reason comes from explain_decision /
what_if / audit_run, or is read straight off the stored record for display.

Sections 1-4 work with no API key, no network, no new dependency. Section 5 is
the chat box; it degrades to a clear "no key" notice while the rest keeps working.
"""

from __future__ import annotations

import streamlit as st

from companion_agent import audit_run, explain_decision, make_companion, what_if
from ui_components import e, empty_state, pill, section
from ui_pages import choose_trend, go


# ---------------------------------------------------------------------------
# helpers -- formatting only
# ---------------------------------------------------------------------------

def _fmt_pct(value) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "—"


def _args_str(args: dict) -> str:
    if not args:
        return "()"
    return "(" + ", ".join(f"{k}={v!r}" for k, v in args.items()) + ")"


def _tool_call_log(tool_calls: list) -> None:
    """The agent's own tool calls, rendered the way the verification trace shows
    its tool calls: an ordered name(args) -> result list."""
    if not tool_calls:
        st.caption("The agent answered without calling any tool.")
        return
    rows = "".join(
        f'<div class="sr-timeline-item"><div class="sr-kicker">TOOL {tc.get("n", i + 1):02d}</div>'
        f'<div class="sr-card-title" style="font-size:1rem">{e(tc.get("tool", ""))}'
        f'{e(_args_str(tc.get("arguments") or {}))}</div>'
        f'<div class="sr-card-copy" style="display:block;min-height:0">{e(tc.get("result_summary", ""))}</div></div>'
        for i, tc in enumerate(tool_calls))
    st.html(f'<div class="sr-timeline">{rows}</div>')


# ---------------------------------------------------------------------------
# SECTION 1 -- explain_decision, four blocks
# ---------------------------------------------------------------------------

def _render_explain(exp: dict) -> None:
    if "error" in exp:
        empty_state("Trend unavailable", exp["error"])
        return
    real = exp["is_it_real"]
    teach = exp["do_we_teach_it"]
    how = exp["how_much"]
    what = exp["what_to_do"]

    section("Is it real?", "Verification confidence, its maturity band, and how the "
            "evidence was gathered.", "BLOCK 1 · VERIFICATION")
    c1, c2 = st.columns([0.55, 1.45], gap="large")
    with c1:
        st.metric("Confidence", _fmt_pct(real["confidence"]))
        st.caption(f"Maturity band {e(real['maturity_band'])}")
    with c2:
        st.html(f'<div class="sr-glass"><div class="sr-kicker">VERIFICATION NOTE</div>'
                f'<div class="sr-card-copy" style="display:block">{e(real["verification_note"] or "—")}</div></div>')
        badges = pill(f"{real['tool_call_count']} tool call(s)", "cyan")
        if real["stopped_early"]:
            badges += pill("Loop stopped early", "amber")
        badges += pill("No LLM ran (deterministic)" if real["no_llm_ran"] else "LLM-driven loop",
                       "amber" if real["no_llm_ran"] else "violet")
        st.html(f'<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">{badges}</div>')
        st.caption(real["mode_plain"])

    section("Do we already teach it?", "Three states that must never collapse into "
            "one. This distinction is the most important thing the Companion says.",
            "BLOCK 2 · CURRICULUM")
    state = teach["state"]
    if state == "found":
        st.success(f"**Searched, and found matching material.**  \n{teach['citation'] or ''}")
    elif state == "searched_no_match":
        st.info("**Searched, and found nothing matching.** This is NOT a claim that the "
                "course has a gap.")
        if teach["reason"]:
            st.caption(teach["reason"])
    elif teach["substate"] == "failed":
        st.error("**The curriculum search FAILED to run.** This is NOT a finding of "
                 "'no match'. The tier is held at 'watch' so no gap is invented.")
        if teach["reason"]:
            st.caption(teach["reason"])
    else:  # skipped
        st.warning("**The curriculum was never searched.** " +
                   (teach["skipped_reason"] or "It did not clear the confidence gate."))
    st.caption(f"searched={teach['searched']} · search_failed={teach['search_failed']} · "
               f"curriculum_checked={teach['curriculum_checked']}")

    section("How much does it matter?", "Maturity and relevance, blended 50/50 into "
            "the total. Recomputed here through evaluation.py's own functions.",
            "BLOCK 3 · EVALUATION")
    m1, m2, m3 = st.columns(3)
    m1.metric("Maturity", f"{how['maturity']}/5")
    m2.metric("Relevance", f"{how['relevance']}/5")
    m3.metric("Total", f"{how['total']}/5")
    st.caption(how["blend"])
    if not how["total_reproduces_stored"]:
        st.warning(f"Recomputed total {how['total']} does not equal the stored total "
                   f"{how['stored_total']}.")

    section("So what should we do?", "The select_tier branch in plain words, then the "
            "tier recomputed from the stored facts.", "BLOCK 4 · RECOMMENDATION")
    st.html(f'<div class="sr-glass"><div class="sr-kicker">STORED ACTION</div>'
            f'<div class="sr-card-title">{e(what["stored_action"])}</div>'
            f'<div class="sr-card-copy" style="display:block">{e(what["branch_reason"])}</div></div>')
    if what["reproducible"]:
        st.success(f"Reproduced: the same facts through select_tier give "
                   f"'{what['recomputed_tier']}'.")
    else:
        st.error(what["warning"])


# ---------------------------------------------------------------------------
# SECTION 2 -- the buried trace, at full fidelity
# ---------------------------------------------------------------------------

def _render_trace(record: dict) -> None:
    section("The buried trace", "The reasoning the pipeline recorded but never showed: "
            "the verification loop and the curriculum queries.", "WHAT THE AGENTS DID")
    trace = record.get("trace")
    if not isinstance(trace, dict):
        empty_state("No trace recorded", "This record predates trace capture, so there "
                    "is no agent reasoning to show.")
        return

    v = trace.get("verification") or {}
    reasoning = v.get("reasoning") or []
    with st.expander(f"Verification reasoning · {len(reasoning)} step(s)", expanded=True):
        if not reasoning:
            st.caption("No verification reasoning was recorded.")
        for step in reasoning:
            thought = step.get("thought") or ""
            tool = step.get("tool") or ""
            obs = step.get("observation") or ""
            if tool:
                st.markdown(f"**{step.get('iteration', '?')}. thought →** {e(thought)}")
                st.markdown(f"&nbsp;&nbsp;&nbsp;**tool** `{e(tool)}{e(_args_str(step.get('tool_args') or {}))}`")
                st.markdown(f"&nbsp;&nbsp;&nbsp;**observation →** {e(obs)}")
            else:
                st.markdown(f"**{step.get('iteration', '?')}. concluded →** {e(thought)}")
                if obs:
                    st.caption(obs)

    c = trace.get("curriculum") or {}
    steps = c.get("steps") or []
    with st.expander(f"Curriculum queries · {len(steps)} search(es)", expanded=False):
        if not steps:
            st.caption("No curriculum queries were issued.")
        for step in steps:
            st.markdown(f"**query →** `{e(step.get('query', ''))}`")
            st.markdown(f"&nbsp;&nbsp;&nbsp;**result →** {e(step.get('result_summary', ''))}")


# ---------------------------------------------------------------------------
# SECTION 3 -- what_if with controls
# ---------------------------------------------------------------------------

def _render_what_if(records: list, index: int, record: dict, signals: list) -> None:
    section("What if?", "Recompute the recommendation under different facts. The maths "
            "runs through the real pipeline functions, never here.", "STRESS TEST")
    stored_conf = record.get("confidence")
    stored_conf = float(stored_conf) if isinstance(stored_conf, (int, float)) else 0.5
    has_stored_match = record.get("match") is not None

    c1, c2, c3 = st.columns(3)
    with c1:
        conf = st.slider("Verification confidence", 0.0, 1.0, value=stored_conf,
                         step=0.05, key=f"wi_conf_{index}")
    with c2:
        checked = st.toggle("Curriculum was searched", value=True,
                            key=f"wi_checked_{index}")
    with c3:
        match = st.toggle("Match exists", value=has_stored_match,
                          disabled=not has_stored_match, key=f"wi_match_{index}",
                          help=None if has_stored_match else
                          "The run stored no match; a match cannot be fabricated.")

    result = what_if(records, index, confidence=conf, has_match=match,
                     curriculum_checked=checked, signals=signals)
    if "error" in result:
        empty_state("Cannot simulate", result["error"])
        return

    tone = "amber" if result["differs_from_stored"] else "green"
    st.html(f'<div class="sr-reveal {tone}">Would recommend: '
            f'{e(result["would_recommend"])}</div>')
    st.caption(result["reason"])
    a, b, c = st.columns(3)
    a.metric("Maturity", f"{result['maturity']}/5")
    b.metric("Relevance", f"{result['relevance']}/5")
    c.metric("Total", f"{result['total']}/5")
    if result["differs_from_stored"]:
        st.info(f"Stored action was '{result['stored_action']}'. Under these inputs the "
                f"tier would be '{result['would_recommend']}'.")
    for note in result.get("notes") or []:
        st.warning(note)


# ---------------------------------------------------------------------------
# SECTION 4 -- audit_run
# ---------------------------------------------------------------------------

_SEV_TONE = {"high": "rose", "medium": "amber", "low": "cyan"}


def _render_audit(records: list, signals: list) -> None:
    section("Audit the whole run", "Every finding is grounded in a stored field or a "
            "pipeline function. Click through to the flagged trend.", "RUN-WIDE FINDINGS")
    audit = audit_run(records, signals)
    counts = audit["counts"]
    st.html('<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">'
            + pill(f"{counts.get('high', 0)} high", "rose")
            + pill(f"{counts.get('medium', 0)} medium", "amber")
            + pill(f"{counts.get('low', 0)} low", "cyan") + '</div>')
    if not audit["findings"]:
        st.success("No findings: every stored recommendation reproduces from its facts.")
        return
    for f in audit["findings"]:
        tone = _SEV_TONE.get(f["severity"], "violet")
        col_text, col_btn = st.columns([4, 1])
        with col_text:
            st.html(f'<div class="sr-glass"><div class="sr-kicker">'
                    f'{e(f["severity"].upper())} · {e(f["kind"])} · TREND #{e(f["index"])}</div>'
                    f'<div class="sr-card-title" style="font-size:1rem">{e(f["title"])}</div>'
                    f'<div class="sr-card-copy" style="display:block">{e(f["detail"])}</div></div>')
        with col_btn:
            st.button("Inspect", key=f"audit_go_{f['index']}_{f['kind']}",
                      on_click=go, args=("Companion agent", f["index"]))


# ---------------------------------------------------------------------------
# SECTION 5 -- the chat box
# ---------------------------------------------------------------------------

_EMPTY = "_(no answer text was returned)_"

# The keys build_turns reads out of ask()'s return. Pinned by a test so a change
# to either side is caught rather than silently dropping the answer.
ASK_KEYS_READ = ("ok", "answer", "tool_calls", "hit_cap", "no_key", "capped", "error")

# kind -> which Streamlit element renders it, so each state LOOKS different.
_KIND_RENDER = {"error": "error", "capped": "warning", "no_key": "warning"}


def _records_sig(records: list) -> tuple:
    """A content signature, stable across st.cache_data's per-rerun COPIES but
    changing when the snapshot changes. Used to key the cached agent + chat so
    an ordinary rerun keeps the SAME live agent (its questions_asked and
    total_cost_usd survive) while a new snapshot still refreshes everything."""
    return tuple((r.get("trend"), r.get("total_score"),
                  r.get("recommended_action")) for r in records)


def _agent_for(records: list, signals: list, meta: dict | None = None):
    # Held in session state, NOT st.cache_data: cache_data returns a fresh copy
    # each rerun, which would reset questions_asked / total_cost_usd and (via the
    # old identity guard) wipe the chat history. Keyed by content + capture date.
    meta = meta or {}
    sig = _records_sig(records) + (meta.get("captured_at"),)
    if (st.session_state.get("companion_agent") is None
            or st.session_state.get("companion_sig") != sig):
        st.session_state["companion_agent"] = make_companion(records, signals,
                                                             snapshot_meta=meta)
        st.session_state["companion_sig"] = sig
        st.session_state["companion_chat"] = []
    return st.session_state["companion_agent"]


def _assistant_turn(answer: dict | None, exc: BaseException | None = None) -> dict:
    """Build the assistant turn from ask()'s return (or an exception). Pure --
    no Streamlit -- and testable. `kind` makes each state render distinctly:
    error / no_key / capped / answer."""
    if exc is not None:
        return {"role": "assistant", "kind": "error", "tool_calls": [],
                "content": f"The lookup raised **{type(exc).__name__}**: {exc}"}
    answer = answer or {}
    tool_calls = answer.get("tool_calls") or []
    if answer.get("ok"):
        kind = "capped" if answer.get("hit_cap") else "answer"
    elif answer.get("no_key"):
        kind = "no_key"
    elif answer.get("capped"):
        kind = "capped"
    else:                                   # error, or any other not-ok result
        kind = "error"
    return {"role": "assistant", "kind": kind, "tool_calls": tool_calls,
            "content": answer.get("answer") or _EMPTY}


def build_turns(agent, question: str) -> tuple[dict, dict]:
    """The chat handler, free of Streamlit: returns (user_turn, assistant_turn).
    The user turn is produced no matter what ask() does -- even if it raises --
    so a failed question is never lost."""
    user = {"role": "user", "content": question}
    try:
        answer, exc = agent.ask(question), None
    except Exception as e:                  # a raising agent still yields a turn
        answer, exc = None, e
    return user, _assistant_turn(answer, exc)


def _render_message_body(turn: dict) -> None:
    body = turn.get("content") or _EMPTY
    how = _KIND_RENDER.get(turn.get("kind", "answer"))
    (getattr(st, how) if how else st.markdown)(body)
    tcs = turn.get("tool_calls") or []
    if tcs:
        with st.expander(f"Tool calls ({len(tcs)})", expanded=False):
            _tool_call_log(tcs)


def _render_turn(turn: dict) -> None:
    with st.chat_message(turn["role"]):
        _render_message_body(turn)


def _render_unavailable(status: dict) -> None:
    """Distinct, specific reasons -- never one generic line."""
    if not status.get("has_sdk"):
        st.warning("The `openai` package is not installed here, so the chat is "
                   "unavailable. Sections 1-4 above need neither key nor network.")
    elif not status.get("has_key"):
        st.info("No OpenAI API key found (checked the environment and BACKEND/.env), "
                "so the chat is unavailable. Sections 1-4 above need no key.")
    else:
        st.warning("The chat is unavailable for an unknown reason (see status below).")
    st.caption(f"key_status: {status}")


def _render_chat(records: list, signals: list, meta: dict | None = None) -> None:
    section("Ask the Companion", "It answers only from its tools, and shows every tool "
            "call it made -- its reasoning is as inspectable as the pipeline's.",
            "COMPANION CHAT")
    agent = _agent_for(records, signals, meta)
    history = st.session_state.setdefault("companion_chat", [])

    # Prior conversation always renders first, from durable session state.
    for turn in history:
        _render_turn(turn)

    status = agent.key_status()
    if not status["ready"]:
        _render_unavailable(status)
        return

    st.caption(f"Model {status['model']} · asked {agent.questions_asked}/{agent.question_cap} "
               f"this session · about ${agent.total_cost_usd:.4f} spent")

    question = st.chat_input("e.g. Which trends can't be reproduced from their facts?")
    if not question:
        return

    # 1. user turn: store AND render immediately, before the request starts, so
    #    the question stays on screen while the spinner runs and survives failure.
    user = {"role": "user", "content": question}
    history.append(user)
    _render_turn(user)

    # 2. assistant bubble with the spinner INSIDE it, where the answer lands.
    # 3. answer / error / cap -> an assistant turn is always appended.
    with st.chat_message("assistant"):
        with st.spinner("The Companion is checking its tools..."):
            _, assistant = build_turns(agent, question)
        _render_message_body(assistant)
    history.append(assistant)
    # No st.rerun(): both turns are already rendered and stored, and the input
    # box stays enabled so a failed question can be retried.


# ---------------------------------------------------------------------------
# PAGE
# ---------------------------------------------------------------------------

def companion(records: list, signals: list, snapshot: dict | None = None) -> None:
    from ui_components import page_intro
    page_intro("THE SIXTH AGENT", "Companion agent",
               "It decides nothing. It explains and stress-tests the five agents' "
               "recorded decisions, rebuilding each one from the pipeline's own functions.")
    if not records:
        empty_state("No recorded run", "There are no recommendations to explain.")
        return
    snapshot = snapshot or {}
    meta = {"captured_at": snapshot.get("captured_at"),
            "source_signals": snapshot.get("source_signals")}
    selected, record = choose_trend(records, "companion")
    exp = explain_decision(records, selected, signals)
    _render_explain(exp)
    _render_trace(record)
    _render_what_if(records, selected, record, signals)
    _render_audit(records, signals)
    _render_chat(records, signals, meta)
