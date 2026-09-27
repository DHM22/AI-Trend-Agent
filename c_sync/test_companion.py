"""
Offline tests for the Companion agent -- 0 API calls, no network.
=================================================================
The analysis tools are pure functions over plain data; the loop is driven by an
injected scripted client, exactly like test_chain.py's _ScriptedClient. Run:

    python c_sync/test_companion.py            # from the repo root
    python c_sync/test_companion.py -v
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for p in (str(_HERE), str(_ROOT / "02_src")):
    if p not in sys.path:
        sys.path.insert(0, p)

import companion_agent as CA

PASS, FAIL = [], []


def check(name, got, want, why=""):
    (PASS if got == want else FAIL).append((name, got, want, why))


def check_true(name, got, why=""):
    check(name, bool(got), True, why)


# ---------------------------------------------------------------------------
# synthetic records -- shaped exactly like a snapshot recommendation
# ---------------------------------------------------------------------------

def _match(exact=None, similarity=0.7, content_type="slides"):
    m = {"week": 3, "topic": "RAG", "source_file": "rag.pdf", "slide_number": 12,
         "matched_text": "chunking", "similarity": similarity,
         "exact_match": exact, "content_type": content_type,
         "citation": "Week 3 / RAG / slide 12"}
    return m


def _rec(trend, confidence, action, match=None, *, searched=True, search_failed=False,
         skipped_reason="", mode="agentic (LLM-driven tool loop)", v_stopped=False,
         c_stopped=False, reasoning=None, csteps=None, reason=""):
    trace = {
        "verification": {"steps": [{"n": 1, "tool": "github_lookup"}] if reasoning else [],
                         "stopped_early": v_stopped, "mode": mode,
                         "reasoning": reasoning or []},
        "curriculum": {"searched": searched, "skipped_reason": skipped_reason,
                       "steps": csteps or [], "reason": reason,
                       "stopped_early": c_stopped, "search_failed": search_failed},
    }
    total = round(0.5 * _maturity(confidence) + 0.5 * _relevance(match), 2)
    return {"trend": trend, "confidence": confidence, "verification_note": "note",
            "evidence": [], "recommended_action": action, "action_plan": [],
            "match": match, "total_score": total, "trace": trace}


def _maturity(c):
    from agents.evaluation import _maturity_score
    return _maturity_score(c)


def _relevance(m):
    from agents.evaluation import _relevance_score
    from companion_agent import _match_object
    return _relevance_score(_match_object({"match": m}))


# ---------------------------------------------------------------------------
# explain_decision
# ---------------------------------------------------------------------------

def test_explain_three_states_and_reproduction():
    # found: mature + strong slide match -> update_existing_material
    found = _rec("Found", 0.9, "update_existing_material", _match(similarity=0.7))
    # searched, nothing, version bump -> watch
    nomatch = _rec("langchain v1.2.3", 0.9, "watch", None, searched=True)
    # never searched (confidence gate)
    skipped = _rec("Low conf item", 0.2, "watch", None, searched=False,
                   skipped_reason="confidence 0.2 below 0.4")
    # searched but the search FAILED
    failed = _rec("Failed search", 0.9, "watch", None, searched=True, search_failed=True,
                  reason="could not run")
    recs = [found, nomatch, skipped, failed]

    e0 = CA.explain_decision(recs, 0)
    check("explain: found state", e0["do_we_teach_it"]["state"], "found")
    check("explain: found reproduces stored action", e0["what_to_do"]["reproducible"], True)
    check("explain: maturity from confidence 0.9", e0["how_much"]["maturity"], 5)

    e1 = CA.explain_decision(recs, 1)
    check("explain: searched-no-match state", e1["do_we_teach_it"]["state"], "searched_no_match")
    check("explain: curriculum_checked true when searched ok", e1["do_we_teach_it"]["curriculum_checked"], True)

    e2 = CA.explain_decision(recs, 2)
    check("explain: skipped is not_checked/skipped", (e2["do_we_teach_it"]["state"],
          e2["do_we_teach_it"]["substate"]), ("not_checked", "skipped"))
    check("explain: skipped is not curriculum_checked", e2["do_we_teach_it"]["curriculum_checked"], False)

    e3 = CA.explain_decision(recs, 3)
    check("explain: failed is not_checked/failed", (e3["do_we_teach_it"]["state"],
          e3["do_we_teach_it"]["substate"]), ("not_checked", "failed"))
    check("explain: failed is NOT the same as skipped", e3["do_we_teach_it"]["substate"] ==
          e2["do_we_teach_it"]["substate"], False,
          "a failed search and a skipped search must render differently")


def test_explain_flags_irreproducible_action():
    # store the WRONG action for the facts: mature + strong match should update,
    # but the record claims 'watch'.
    bad = _rec("Mislabelled", 0.9, "watch", _match(similarity=0.7))
    e = CA.explain_decision([bad], 0)
    check("explain: irreproducible action flagged", e["what_to_do"]["reproducible"], False)
    check_true("explain: warning names both tiers", "update_existing_material" in
               (e["what_to_do"]["warning"] or ""))


def test_explain_bad_index():
    check_true("explain: out-of-range index -> error", "error" in CA.explain_decision([], 5))


# ---------------------------------------------------------------------------
# what_if
# ---------------------------------------------------------------------------

def test_what_if_confidence_moves_tier():
    # a strong slide match but low confidence -> watch (below maturity floor)
    rec = _rec("Borderline", 0.2, "watch", _match(similarity=0.7))
    low = CA.what_if([rec], 0)
    check("what_if: stored low confidence -> watch", low["would_recommend"], "watch")
    high = CA.what_if([rec], 0, confidence=0.9)
    check("what_if: raising confidence unlocks update", high["would_recommend"],
          "update_existing_material")
    check_true("what_if: reports the change from stored", high["changed_from_stored"]["confidence"])


def test_what_if_never_fabricates_match():
    rec = _rec("No match stored", 0.9, "watch", None, searched=True)
    r = CA.what_if([rec], 0, has_match=True)
    check("what_if: has_match on a matchless run stays matchless",
          r["inputs"]["has_match"], False)
    check_true("what_if: refusal is noted", any("cannot be fabricated" in n for n in r["notes"]))


def test_what_if_curriculum_checked_toggle():
    # mature, in-domain, no match: checked -> add_new_lesson, unchecked -> watch
    rec = _rec("RAG evaluation harness for agents", 0.9, "add_new_lesson", None, searched=True)
    checked = CA.what_if([rec], 0, curriculum_checked=True)
    unchecked = CA.what_if([rec], 0, curriculum_checked=False)
    check("what_if: checked+gap -> new lesson", checked["would_recommend"], "add_new_lesson")
    check("what_if: unchecked -> watch (never invent a gap)", unchecked["would_recommend"], "watch")


# ---------------------------------------------------------------------------
# audit_run
# ---------------------------------------------------------------------------

def test_audit_detects_each_finding_kind():
    recs = [
        _rec("Failed one", 0.9, "watch", None, searched=True, search_failed=True, reason="429"),
        _rec("Skipped one", 0.2, "watch", None, searched=False, skipped_reason="gate"),
        _rec("Deterministic one", 0.9, "update_existing_material", _match(similarity=0.7),
             mode="deterministic (no LLM; scripted tool loop)"),
        _rec("Early one", 0.9, "watch", None, searched=True, v_stopped=True),
        # confident but a tool observation did not confirm
        _rec("Confident unconfirmed", 0.75, "watch", None, searched=True,
             reasoning=[{"iteration": 1, "thought": "check", "tool": "github_lookup",
                         "tool_args": {}, "observation": "no matching repository found"}]),
        # add_new_lesson yet an exact: hit exists
        _rec("Lesson over exact", 0.9, "add_new_lesson", None, searched=True,
             csteps=[{"n": 1, "query": "faiss", "result_summary": "1 hit (exact:FAISS)"}]),
        # irreproducible: strong match labelled watch
        _rec("Irreproducible", 0.9, "watch", _match(similarity=0.7)),
        # domain term buried in a longer word, and nothing else in-domain
        _rec("storage benchmarks", 0.2, "watch", None, searched=False),
    ]
    kinds = {f["kind"] for f in CA.audit_run(recs)["findings"]}
    for expected in ("curriculum_search_failed", "curriculum_search_skipped",
                     "deterministic_fallback", "verification_stopped_early",
                     "unconfirmed_but_confident", "new_lesson_over_exact_hit",
                     "irreproducible_action", "domain_term_inside_word"):
        check_true(f"audit: detects {expected}", expected in kinds)


def test_audit_domain_bug_needs_no_other_trigger():
    # "agents" is a whole-word domain term, so the buried "agent" is harmless.
    ok = _rec("Scaling Agents in Europe", 0.2, "watch", None, searched=False)
    kinds = {f["kind"] for f in CA.audit_run([ok])["findings"]}
    check("audit: buried term ignored when a whole-word term also fires",
          "domain_term_inside_word" in kinds, False)


def test_audit_clean_run_has_no_findings():
    clean = _rec("langchain v1.2.3", 0.9, "watch", None, searched=True)  # version bump -> watch
    check("audit: a reproducible watch item is clean", CA.audit_run([clean])["total"], 0)


# ---------------------------------------------------------------------------
# the loop -- scripted client, no key
# ---------------------------------------------------------------------------

def _msg(content=None, tool_calls=None):
    return types.SimpleNamespace(content=content, tool_calls=tool_calls)


def _reply(content=None, tool_calls=None, pt=20, ct=8):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=_msg(content, tool_calls))],
        usage=types.SimpleNamespace(prompt_tokens=pt, completion_tokens=ct))


def _tc(name, arguments, cid="c1"):
    return types.SimpleNamespace(id=cid, function=types.SimpleNamespace(
        name=name, arguments=arguments))


class _ScriptedClient:
    def __init__(self, *script):
        self.script = list(script)
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    def _create(self, **_kw):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_loop_calls_tool_then_answers():
    rec = _rec("Mislabelled", 0.9, "watch", _match(similarity=0.7))
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("explain_decision", '{"index": 0}')]),
        _reply(content="Trend #0 cannot be reproduced from its facts."))
    agent = CA.make_companion([rec], [], client=client)
    out = agent.ask("Is trend 0 reproducible?")
    check("loop: returns ok", out["ok"], True)
    check("loop: records the tool call name", out["tool_calls"][0]["tool"], "explain_decision")
    check("loop: records the tool call arguments", out["tool_calls"][0]["arguments"], {"index": 0})
    check_true("loop: answer text passed through", "#0" in out["answer"])
    check_true("loop: an approximate cost is reported", out["cost_usd"] > 0)


def test_loop_no_key_is_graceful():
    # Simulate "no key" by setting it EMPTY, not by popping it: the companion's
    # key_status() calls _load_env() -> load_dotenv(.env), and popping lets that
    # repopulate a real key from a developer's .env. load_dotenv(override=False)
    # leaves an already-present (empty) var alone, and bool("") is False, so the
    # companion sees no key. (Popping made this test fail on machines with .env.)
    import os
    saved = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = ""
    try:
        agent = CA.make_companion([_rec("x", 0.9, "watch", None)], [])
        out = agent.ask("anything")
    finally:
        if saved is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved
    check("loop: no key -> not ok", out["ok"], False)
    check_true("loop: no key flagged", out.get("no_key"))
    check("loop: no tool calls without a key", out["tool_calls"], [])


def test_loop_never_returns_empty_when_cap_hit():
    # A model that ALWAYS calls a tool, plus a forced final call that comes back
    # empty -- the real exhaustion failure. The user must still get text.
    rec = _rec("x", 0.9, "watch", None)

    class KeepsCallingTools:
        def __init__(self):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create))

        def _create(self, **kw):
            if "tools" in kw:  # a normal round: emit yet another tool call
                return _reply(tool_calls=[_tc("audit_run", "{}")])
            return _reply(content="")  # forced final call: empty content

    agent = CA.make_companion([rec], [], client=KeepsCallingTools(), max_tool_rounds=3)
    out = agent.ask("audit everything in detail")
    answer = out["answer"] or ""
    check_true("loop: answer is non-empty when the cap is hit", answer.strip())
    check("loop: cap hit is flagged", out.get("hit_cap"), True)
    check("loop: made a tool call every round up to the cap", len(out["tool_calls"]), 3)
    # the cap message must report WHAT it found so far, not only that it ran out
    check_true("loop: cap message names the tool it called", "audit_run" in answer)
    check_true("loop: cap message includes a gathered result",
               out["tool_calls"][0]["result_summary"] in answer,
               "partial findings must survive into the message")


def test_default_round_cap_gives_headroom():
    # a two-part question (explain + what_if) needs ~4 rounds; the default must
    # leave real headroom above that so the user gets an answer, not the cap.
    from agents.companion import MAX_TOOL_ROUNDS
    check_true("loop: default cap has headroom for explain + what_if",
               MAX_TOOL_ROUNDS >= 8)


def test_loop_salvages_answer_given_with_a_final_tool_call():
    # The model puts its answer in content but ALSO calls a tool; the forced
    # final call is empty. The content must not be lost to silence.
    rec = _rec("x", 0.9, "watch", None)

    class AnswerThenTool:
        def __init__(self):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create))

        def _create(self, **kw):
            if "tools" in kw:
                return _reply(content="Trend #0 stays a watch.",
                              tool_calls=[_tc("get_trend", '{"index": 0}')])
            return _reply(content="")

    out = CA.make_companion([rec], [], client=AnswerThenTool(), max_tool_rounds=2).ask("q")
    check_true("loop: content given with a tool call is salvaged, not dropped",
               "#0" in (out["answer"] or ""))


def test_loop_question_cap():
    rec = _rec("x", 0.9, "watch", None)
    # A grounded first answer (tool call then reply); a bare content-only reply is
    # now refused as ungrounded, so the first turn must actually call a tool.
    client = _ScriptedClient(_reply(tool_calls=[_tc("get_trend", '{"index": 0}')]),
                             _reply(content="ok"))
    agent = CA.make_companion([rec], [], client=client, question_cap=1)
    first = agent.ask("one")
    second = agent.ask("two")
    check("loop: first question answered", first["ok"], True)
    check_true("loop: second question hits the cap", second.get("capped"))


# ---------------------------------------------------------------------------
# curriculum_status -- the direct "was it checked" tool, and audit typing
# ---------------------------------------------------------------------------

def _one_of_each_state():
    return [
        _rec("Found", 0.9, "update_existing_material", _match(similarity=0.7)),  # found
        _rec("langchain v1.2.3", 0.9, "watch", None, searched=True),             # searched_no_match
        _rec("Low conf", 0.2, "watch", None, searched=False,                     # never_searched
             skipped_reason="confidence 0.2 below 0.4"),
        _rec("Broke", 0.9, "watch", None, searched=True, search_failed=True,     # search_failed
             reason="429 spend limit"),
    ]


def test_curriculum_status_answers_never_checked_directly():
    recs = _one_of_each_state()
    never = CA.curriculum_status(recs, "never_searched")
    check("curriculum_status: exactly one never_searched trend", never["match_count"], 1)
    check("curriculum_status: it is the right trend", never["trends"][0]["index"], 2)
    check_true("curriculum_status: gives the reason", "0.4" in never["trends"][0]["reason"]
               or "confidence" in never["trends"][0]["reason"])
    # the four states are counted separately, never collapsed
    check("curriculum_status: per-state counts", never["counts"],
          {"found": 1, "searched_no_match": 1, "never_searched": 1, "search_failed": 1})
    check_true("curriculum_status: search_failed is distinct from never_searched",
               CA.curriculum_status(recs, "search_failed")["trends"][0]["index"] == 3)
    check_true("curriculum_status: definitions are returned", "never_searched" in never["definitions"])
    check_true("curriculum_status: rejects a bad state", "error" in CA.curriculum_status(recs, "bogus"))


def test_audit_findings_carry_curriculum_state():
    # a searched-and-matched trend that is ALSO mislabelled -> irreproducible_action
    bad = _rec("Mislabelled", 0.9, "watch", _match(similarity=0.7))          # found + irreproducible
    skipped = _rec("Low conf", 0.2, "watch", None, searched=False, skipped_reason="gate")
    audit = CA.audit_run([bad, skipped])
    check_true("audit: result carries a 'not a curriculum state' note", "note" in audit)
    check_true("audit: note warns against counting findings as states",
               "not" in audit["note"].lower() and "curriculum" in audit["note"].lower())
    irr = [f for f in audit["findings"] if f["kind"] == "irreproducible_action"]
    check_true("audit: a searched trend's finding carries curriculum_searched=True",
               irr and irr[0]["curriculum_searched"] is True)
    check("audit: that finding's curriculum_state is 'found'", irr[0]["curriculum_state"], "found")
    check_true("audit: every finding is flagged NOT a curriculum state",
               all(f["is_curriculum_state"] is False for f in audit["findings"]))
    # a stopped/skipped trend must NOT read as searched
    sk = [f for f in audit["findings"] if f["index"] == 1]
    check_true("audit: a never-searched trend's findings say curriculum_searched=False",
               sk and all(f["curriculum_searched"] is False for f in sk))


def test_agent_calls_curriculum_status_for_the_never_checked_question():
    # The exact question from the bug report. Script the model to reach for the
    # right tool; assert the loop routes it and the answer rests on ONE trend.
    recs = _one_of_each_state()
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("curriculum_status", '{"state": "never_searched"}')]),
        _reply(content="Exactly one trend, #2, was never checked (confidence below 0.4)."))
    agent = CA.make_companion(recs, [], client=client)
    out = agent.ask("Which trends were never checked against the curriculum, and why?")
    check("agent: routed to curriculum_status", out["tool_calls"][0]["tool"], "curriculum_status")
    check("agent: with the never_searched state", out["tool_calls"][0]["arguments"],
          {"state": "never_searched"})
    check_true("agent: answer reflects a single trend", "#2" in out["answer"])
    # and the tool is actually offered to the model
    from agents.companion import _COMPANION_TOOLS
    names = {t["function"]["name"] for t in _COMPANION_TOOLS}
    check_true("agent: curriculum_status is an offered tool", "curriculum_status" in names)


def test_all_states_question_routes_to_all_and_breaks_down():
    # "How many trends have no curriculum match?" spans searched_no_match AND
    # never_searched (and search_failed). It must route to state='all' and the
    # answer must name each state's number, not one undifferentiated figure.
    recs = _one_of_each_state()  # 1 in each state

    # curriculum_status('all') must expose every state's count so a correct,
    # broken-down answer can be formed without inference.
    allst = CA.curriculum_status(recs, "all")
    no_match = (allst["counts"]["searched_no_match"]
                + allst["counts"]["never_searched"]
                + allst["counts"]["search_failed"])
    check("curriculum_status(all): 'no match' total is the sum of three states", no_match, 3)

    breakdown = (f"{no_match} with no match: {allst['counts']['searched_no_match']} "
                 f"searched-and-found-nothing + {allst['counts']['never_searched']} never "
                 f"searched + {allst['counts']['search_failed']} search failed.")
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("curriculum_status", '{"state": "all"}')]),
        _reply(content=breakdown))
    out = CA.make_companion(recs, [], client=client).ask(
        "How many trends have no curriculum match?")
    check("all-states: routed to curriculum_status", out["tool_calls"][0]["tool"],
          "curriculum_status")
    check("all-states: with state='all'", out["tool_calls"][0]["arguments"], {"state": "all"})
    ans = out["answer"]
    check_true("all-states: answer names the combined total", "3" in ans)
    check_true("all-states: answer keeps searched_no_match distinct",
               "searched-and-found-nothing" in ans or "searched" in ans)
    check_true("all-states: answer keeps never_searched distinct", "never searched" in ans)


def test_never_searched_answer_does_not_use_missing_match_as_evidence():
    # For a never_searched trend the absent match is NOT evidence. The grounding
    # the agent is told to use (explain_decision) must reflect that: coverage is
    # unknown, and the reason is maturity, not the missing match.
    rec = _rec("Low conf item", 0.15, "watch", None, searched=False,
               skipped_reason="confidence 0.15 below 0.4")
    ex = CA.explain_decision([rec], 0)
    teach, what = ex["do_we_teach_it"], ex["what_to_do"]
    check("never_searched: coverage flagged unknown", teach["coverage_unknown"], True)
    check("never_searched: missing match is not evidence", teach["missing_match_is_evidence"], False)
    check_true("never_searched: evidence_note says the absent match is not evidence",
               "not" in teach["evidence_note"].lower() and "evidence" in teach["evidence_note"].lower())
    check_true("never_searched: the reason is maturity, not the match",
               "maturity" in what["branch_reason"].lower())
    check("never_searched: the branch reason never cites a match",
          "match" in what["branch_reason"].lower(), False,
          "a never-searched trend's tier reason must not rest on the absent match")


def test_should_we_question_routes_to_explain_decision():
    # A "should we..." question must ground on explain_decision (which names the
    # select_tier branch), not answer from get_trend's raw fields.
    rec = _rec("Low conf item", 0.15, "watch", None, searched=False,
               skipped_reason="confidence 0.15 below 0.4")
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("explain_decision", '{"index": 0}')]),
        _reply(content="No: trend #0 is below the maturity floor; curriculum coverage "
                       "is unknown (never searched), which is not itself a reason."))
    out = CA.make_companion([rec], [], client=client).ask(
        "Should we add a new lesson for trend #0?")
    check("should-we: routed to explain_decision", out["tool_calls"][0]["tool"], "explain_decision")
    check_true("should-we: answer does not treat the missing match as evidence",
               "not" in out["answer"].lower())


def test_false_premise_is_corrected_not_echoed():
    # User asserts a wrong confidence (0.95); the record says 0.6. The model gets
    # the real value from get_trend, and a compliant answer names the wrong figure
    # ONLY inside the correction, using the recorded value everywhere else.
    rec = _rec("Trend ten", 0.6, "watch", None, searched=True)
    correction = ("The record shows confidence 0.6, not 0.95. At 0.6 the trend is "
                  "below the maturity floor, so the recommendation stays 'watch'.")
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("get_trend", '{"index": 0}')]),
        _reply(content=correction))
    agent = CA.make_companion([rec], [], client=client)
    out = agent.ask("Since the verification agent gave trend 0 a score of 0.95, should we act?")
    check("false-premise: routed to get_trend for the real value",
          out["tool_calls"][0]["tool"], "get_trend")
    ans = out["answer"]
    check_true("false-premise: the recorded value is stated", "0.6" in ans)
    check("false-premise: the wrong figure appears exactly once", ans.count("0.95"), 1)
    check_true("false-premise: and only inside the correction ('not 0.95')", "not 0.95" in ans)


def test_rerun_request_says_it_cannot_and_names_the_snapshot_date():
    rec = _rec("Trend 28", 0.15, "watch", None, searched=False, skipped_reason="gate")
    captured = "2026-09-21T19:32:16+00:00"
    # snapshot_info is the grounding surface: it must state read-only, refuse the
    # re-run, name the date, and never use self-claim words like 're-ran'.
    info = CA.snapshot_info({"captured_at": captured, "source_signals": "signals.json"})
    check("snapshot_info: read-only", info["read_only"], True)
    check("snapshot_info: cannot re-run", info["can_rerun"], False)
    check_true("snapshot_info: names the capture date", captured in info["statement"])
    check_true("snapshot_info: points at the CLI re-capture step",
               "demo_snapshot.py --capture" in info["how_to_refresh"])
    for banned in ("re-ran", "re-evaluated", "re-checked"):
        check("snapshot_info: makes no false self-claim (%s)" % banned,
              banned in (info["statement"] + info["how_to_refresh"]).lower(), False)

    # And a "re-run" question routes to snapshot_info, with a compliant answer.
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("snapshot_info", "{}")]),
        _reply(content=(f"I cannot re-run anything -- I only read the recorded run, "
                        f"captured {captured}. A fresh capture is a CLI step you run: "
                        f"python 02_src/demo_snapshot.py --capture.")))
    agent = CA.make_companion([rec], [], client=client,
                              snapshot_meta={"captured_at": captured})
    out = agent.ask("Re-run the verification for trend 0 with the latest data.")
    check("re-run: routed to snapshot_info", out["tool_calls"][0]["tool"], "snapshot_info")
    ans = out["answer"].lower()
    check_true("re-run: answer says nothing was re-run", "cannot re-run" in ans)
    check_true("re-run: answer names the snapshot date", captured in out["answer"])
    check_true("re-run: answer never claims it re-ran/updated",
               "re-ran" not in ans and "re-evaluated" not in ans)


def test_refresh_answer_contains_the_real_captured_at():
    # Failure 1: fabricated date. A refresh request must ground the date on
    # snapshot_info's captured_at, and the answer must carry that real value.
    rec = _rec("Trend", 0.9, "watch", None)
    captured = "2026-09-21T19:32:16+00:00"
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("snapshot_info", "{}")]),
        _reply(content=f"I can't refresh anything; the run was captured {captured}."))
    out = CA.make_companion([rec], [], client=client,
                            snapshot_meta={"captured_at": captured}).ask(
        "Refresh the data to the latest.")
    check("refresh: grounded via snapshot_info", out["tool_calls"][0]["tool"], "snapshot_info")
    check_true("refresh: answer contains the REAL captured_at", captured in out["answer"])


def test_prioritisation_makes_a_tool_call_and_cites_scores():
    # Failure 2b/2c: a prioritisation answer must call rank_trends and cite the
    # stored scores, not invent a ranking from file order.
    recs = [
        _rec("A", 0.9, "watch", None),                                   # total 2.5
        _rec("B", 0.9, "update_existing_material", _match(similarity=0.7)),  # total 5.0
        _rec("C", 0.9, "add_optional_content", _match(similarity=0.5)),   # mid
    ]
    ranked = CA.rank_trends(recs)
    # rank_trends orders by tier then score: update_existing_material first.
    check("rank_trends: most urgent tier leads", ranked["trends"][0]["index"], 1)
    check_true("rank_trends: returns the stored total_score for tracing",
               ranked["trends"][0]["total_score"] is not None)

    lead = ranked["trends"][0]
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("rank_trends", '{"limit": 3}')]),
        _reply(content=f"By the record: #{lead['index']} leads (total {lead['total_score']}/5)."))
    out = CA.make_companion(recs, [], client=client).ask(
        "Which three trends should I prioritise for next semester?")
    check_true("prioritise: at least one tool call was made", len(out["tool_calls"]) >= 1)
    check("prioritise: it was rank_trends", out["tool_calls"][0]["tool"], "rank_trends")
    check_true("prioritise: answer cites a stored score", str(lead["total_score"]) in out["answer"])


def test_zero_tool_answer_is_refused_not_invented():
    # Failure 2a: if the model answers with NO tool call, the loop nudges once
    # and, if still ungrounded, refuses instead of delivering an invented answer.
    rec = _rec("A", 0.9, "watch", None)

    class _NeverCallsTools:
        def __init__(self):
            self.calls = 0
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._c))

        def _c(self, **kw):
            self.calls += 1
            return _reply(content="Prioritise trends #0, #1, #2.")  # invented, no tool

    client = _NeverCallsTools()
    out = CA.make_companion([rec], [], client=client).ask("Which trends should I prioritise?")
    check("zero-tool: the loop pushed back (called the model twice)", client.calls, 2)
    check("zero-tool: no tool calls recorded", out["tool_calls"], [])
    check("zero-tool: flagged ungrounded", out.get("grounded"), False)
    check_true("zero-tool: the invented answer is NOT delivered", "#0, #1, #2" not in out["answer"])
    check_true("zero-tool: an honest 'could not ground' message is returned",
               "ground" in out["answer"].lower())


def test_implicit_premise_gets_explicit_correction():
    # Failure 3: user asserts a wrong TIER; the answer must open with an explicit
    # correction naming both values, not silently answer about the right one.
    rec = _rec("Trend 22", 0.2, "watch", None, searched=True)  # stored: watch
    client = _ScriptedClient(
        _reply(tool_calls=[_tc("get_trend", '{"index": 0}')]),
        _reply(content=("The record shows watch, not a new lesson. Its confidence is "
                        "0.2, below the maturity floor, which is why the tier is watch.")))
    out = CA.make_companion([rec], [], client=client).ask(
        "Trend 0 was recommended for a new lesson, so why is its confidence so low?")
    ans = out["answer"].lower()
    check_true("implicit-correction: opens by naming the real tier", "watch" in ans)
    check_true("implicit-correction: explicitly negates the false premise",
               "not a new lesson" in ans)


def test_audit_payload_to_model_has_per_finding_records():
    # The follow-up: what reaches the MODEL must be the full findings (kind,
    # index, curriculum_state), not only the counts shown in the UI label.
    recs = _one_of_each_state()

    class _CapturingClient:
        def __init__(self):
            self.seen_tool_messages = []
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create))
            self._round = 0

        def _create(self, **kw):
            for m in kw.get("messages", []):
                if m.get("role") == "tool":
                    self.seen_tool_messages.append(m["content"])
            self._round += 1
            if self._round == 1:
                return _reply(tool_calls=[_tc("audit_run", "{}")])
            return _reply(content="done")

    client = _CapturingClient()
    CA.make_companion(recs, [], client=client).ask("audit the run")
    payload = " ".join(client.seen_tool_messages)
    check_true("payload: the model received the audit tool result", bool(payload))
    check_true("payload: it contains per-finding records, not just counts",
               '"kind"' in payload and '"index"' in payload)
    check_true("payload: findings carry the self-describing curriculum_state",
               '"curriculum_state"' in payload)
    check_true("payload: the anti-miscount note reaches the model",
               '"note"' in payload)


# ---------------------------------------------------------------------------
# the CHAT PAGE handler (ui_companion.build_turns) -- Streamlit-free
# ---------------------------------------------------------------------------

import ui_companion as UIC


class _FakeCompanion:
    """Stands in for CompanionAgent: returns a fixed ask() result, or raises."""

    def __init__(self, result=None, raises=None, ready=True, has_sdk=True, has_key=True):
        self._result = result
        self._raises = raises
        self._status = {"has_key": has_key, "has_sdk": has_sdk,
                        "model": "gpt-4o-mini", "ready": ready}
        self.records, self.signals = [], []
        self.questions_asked, self.question_cap = 0, 20
        self.total_cost_usd, self.model = 0.0, "gpt-4o-mini"

    def key_status(self):
        return dict(self._status)

    def ask(self, question):
        self.questions_asked += 1
        if self._raises:
            raise self._raises
        return self._result


_SHAPE = {  # the exact dict shape verified from the shell
    "ok": True,
    "answer": "Trend #6 got 0.75 confidence: one primary source, release CONFIRMED.",
    "tool_calls": [{"n": 1, "tool": "get_trend", "arguments": {"index": 6},
                    "result_summary": "#6 langchain-ai/langsmith-sdk: v0.14.0"}],
    "cost_usd": 0.000569, "questions_asked": 1, "question_cap": 20,
}


def test_chat_handler_delivers_answer_text():
    q = "Why did trend 6 get its confidence?"
    user, asst = UIC.build_turns(_FakeCompanion(result=_SHAPE), q)
    check("chat: user turn keeps the question", user["content"], q)
    check("chat: answer TEXT reaches the assistant turn", asst["content"], _SHAPE["answer"])
    check("chat: a normal answer is kind 'answer'", asst["kind"], "answer")
    check("chat: tool calls are preserved", asst["tool_calls"][0]["tool"], "get_trend")


def test_chat_handler_shows_error_and_keeps_question():
    q = "explain 6"
    user, asst = UIC.build_turns(_FakeCompanion(raises=RuntimeError("connection reset")), q)
    check("chat: the question survives an exception", user["content"], q)
    check("chat: an exception becomes an error turn", asst["kind"], "error")
    check_true("chat: error turn names the exception class", "RuntimeError" in asst["content"])
    check_true("chat: error turn names the reason", "connection reset" in asst["content"])


def test_chat_handler_distinguishes_not_ok_states():
    def turn(result):
        return UIC.build_turns(_FakeCompanion(result=result), "q")[1]
    nokey = turn({"ok": False, "no_key": True, "answer": "No key.", "tool_calls": []})
    apierr = turn({"ok": False, "error": "429", "answer": "The API call failed: 429", "tool_calls": []})
    capped = turn({"ok": False, "capped": True, "answer": "Session cap.", "tool_calls": []})
    hitcap = turn({"ok": True, "hit_cap": True, "answer": "Partial findings.", "tool_calls": []})
    normal = turn({"ok": True, "answer": "Here you go.", "tool_calls": []})
    check("chat: no-key state", nokey["kind"], "no_key")
    check("chat: API-error state", apierr["kind"], "error")
    check("chat: session-cap state", capped["kind"], "capped")
    check("chat: round-cap partial state", hitcap["kind"], "capped")
    check("chat: normal state", normal["kind"], "answer")
    check_true("chat: the states are not one generic kind",
               len({nokey["kind"], apierr["kind"], capped["kind"], normal["kind"]}) >= 3)


def test_chat_contract_keys_pinned():
    # Every key the page reads must be one ask() can actually produce, across
    # its real return paths -- so a rename on either side fails here.
    rec = _rec("x", 0.9, "watch", None)
    produced = set()
    produced |= set(CA.make_companion([rec], [], client=_ScriptedClient(_reply(content="hi"))).ask("q"))
    produced |= set(CA.make_companion([rec], [], client=_ScriptedClient(RuntimeError("x"))).ask("q"))
    produced |= set(CA.make_companion([rec], [], client=_ScriptedClient(_reply(content="hi")),
                                      question_cap=0).ask("q"))

    class _KeepTools:  # exhaust the round cap -> the hit_cap path
        def __init__(self):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._c))

        def _c(self, **kw):
            return _reply(tool_calls=[_tc("audit_run", "{}")]) if "tools" in kw else _reply(content="")

    produced |= set(CA.make_companion([rec], [], client=_KeepTools(), max_tool_rounds=2).ask("q"))
    import os
    # Empty (not popped) so _load_env()/load_dotenv can't repopulate a real key
    # from a developer's .env; bool("") is False, so this is the no-key path.
    saved = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = ""
    try:
        produced |= set(CA.make_companion([rec], []).ask("q"))  # no-key path
    finally:
        if saved is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved
    missing = [k for k in UIC.ASK_KEYS_READ if k not in produced]
    check("contract: every page-read key is produced by ask()", missing, [])
    # a minimal ok dict must not raise (defensive against absent optional keys)
    asst = UIC._assistant_turn({"ok": True, "answer": "hi"})
    check("contract: minimal ok dict is tolerated", (asst["content"], asst["tool_calls"]), ("hi", []))


def test_chat_answer_text_reaches_rendered_output():
    # End to end through the page: submit a question with a fake ready agent and
    # confirm the answer TEXT lands in the rendered markdown, with the question.
    try:
        from streamlit.testing.v1 import AppTest
        from ui_adapter import load_recorded_run
    except Exception as ex:
        PASS.append(("apptest: skipped (%s)" % type(ex).__name__, None))
        return
    # Deterministic: this test injects a FAKE agent (with its own ready/has_key)
    # to render a canned answer. If a real OPENAI_API_KEY is present in the env
    # (incl. one _load_env() pulls from a developer's .env), the page rebuilds a
    # real-client agent and the injected fake is discarded, so the marker never
    # renders -- which made this test depend on the machine's key (flaky). Force
    # the key EMPTY so the injected fake is the agent under test. bool("") is
    # False, and load_dotenv(override=False) leaves an existing empty var alone.
    # Restored in finally.
    import os
    _saved_key = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = ""
    try:
        snap, _sig_src = load_recorded_run()
        recs = snap.get("recommendations") or []
        marker = "RENDERED-ANSWER-MARKER-6"
        fake = _FakeCompanion(result={"ok": True, "answer": marker,
                                  "tool_calls": [{"n": 1, "tool": "get_trend",
                                                  "arguments": {"index": 6},
                                                  "result_summary": "#6 langsmith-sdk"}],
                                  "questions_asked": 1, "question_cap": 20})
        at = AppTest.from_file(str(_ROOT / "c_sync" / "app.py"), default_timeout=90)
        at.session_state["page"] = "Companion agent"
        at.session_state["companion_agent"] = fake
        at.session_state["companion_sig"] = UIC._records_sig(recs)
        at.session_state["companion_chat"] = []
        at.run()
        if not at.chat_input:
            PASS.append(("apptest: skipped (no chat_input in this Streamlit)", None))
            return
        q = "Why did trend 6 get its confidence?"
        at.chat_input[0].set_value(q).run()
        md = " ".join(m.value for m in at.markdown)
        check_true("apptest: the answer text reaches the rendered output", marker in md)
        check_true("apptest: the question stays visible", q in md)
        check_true("apptest: no exception on the page", not at.exception)
    finally:
        if _saved_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = _saved_key


# ---------------------------------------------------------------------------
# against the REAL committed snapshot
# ---------------------------------------------------------------------------

def test_real_snapshot_states_and_audit():
    try:
        from ui_adapter import load_recorded_run
        snap, signals = load_recorded_run()
    except Exception as ex:
        PASS.append(("real snapshot: skipped (%s)" % type(ex).__name__, None))
        return
    recs = snap.get("recommendations") or []
    check_true("real: snapshot has records", len(recs) > 0)
    states = {CA.explain_decision(recs, i, signals)["do_we_teach_it"]["state"]
              for i in range(len(recs))}
    for s in ("found", "searched_no_match", "not_checked"):
        check_true(f"real: state '{s}' present in the committed run", s in states)
    audit = CA.audit_run(recs, signals)
    check_true("real: audit runs and returns findings dict", "findings" in audit)


# ---------------------------------------------------------------------------

TESTS = [
    test_explain_three_states_and_reproduction,
    test_explain_flags_irreproducible_action,
    test_explain_bad_index,
    test_what_if_confidence_moves_tier,
    test_what_if_never_fabricates_match,
    test_what_if_curriculum_checked_toggle,
    test_audit_detects_each_finding_kind,
    test_audit_domain_bug_needs_no_other_trigger,
    test_audit_clean_run_has_no_findings,
    test_loop_calls_tool_then_answers,
    test_loop_no_key_is_graceful,
    test_loop_never_returns_empty_when_cap_hit,
    test_default_round_cap_gives_headroom,
    test_loop_salvages_answer_given_with_a_final_tool_call,
    test_loop_question_cap,
    test_curriculum_status_answers_never_checked_directly,
    test_audit_findings_carry_curriculum_state,
    test_agent_calls_curriculum_status_for_the_never_checked_question,
    test_all_states_question_routes_to_all_and_breaks_down,
    test_never_searched_answer_does_not_use_missing_match_as_evidence,
    test_should_we_question_routes_to_explain_decision,
    test_false_premise_is_corrected_not_echoed,
    test_rerun_request_says_it_cannot_and_names_the_snapshot_date,
    test_refresh_answer_contains_the_real_captured_at,
    test_prioritisation_makes_a_tool_call_and_cites_scores,
    test_zero_tool_answer_is_refused_not_invented,
    test_implicit_premise_gets_explicit_correction,
    test_audit_payload_to_model_has_per_finding_records,
    test_chat_handler_delivers_answer_text,
    test_chat_handler_shows_error_and_keeps_question,
    test_chat_handler_distinguishes_not_ok_states,
    test_chat_contract_keys_pinned,
    test_chat_answer_text_reaches_rendered_output,
    test_real_snapshot_states_and_audit,
]


def main():
    verbose = "-v" in sys.argv
    errors = []
    for fn in TESTS:
        try:
            fn()
        except Exception as e:
            errors.append((fn.__name__, f"{type(e).__name__}: {e}"))
    if verbose:
        for name, got in PASS:
            print(f"  ok    {name}")
    for name, got, want, why in FAIL:
        print(f"  FAIL  {name}\n          got {got!r}, expected {want!r}"
              + (f"\n          {why}" if why else ""))
    for name, err in errors:
        print(f"  ERROR {name}: {err}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed, {len(errors)} errored")
    return 1 if (FAIL or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
